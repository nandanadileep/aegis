"""
Zep-style Entity-Relation-Fact graph memory layer for Neo4j.

This module builds a dynamic, temporally-aware knowledge graph:

    (Person)-[:HAS_EPISODE]->(Episode)
    (Episode)-[:EXTRACTED]->(Fact)
    (Entity)-[:FACT {valid_from, valid_to, expired_at}]->(Entity)
    (Entity)-[:MENTIONED_IN]->(Episode)

Design choices:
- One label for all semantic nodes: :Entity. The `entity_type` property is
  encrypted separately so we don't need dynamic labels.
- Facts are stored as relationships (edges), not intermediate nodes. This keeps
  the graph compact and makes temporal invalidation natural.
- All plaintext is encrypted per-user via scripts/crypto.py.
- Embeddings are optional. If EMBEDDING_MODEL is set, litellm.embedding is used.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Callable, Tuple

import litellm
import parsedatetime as pdt
from neo4j import GraphDatabase

# Import crypto helpers with fallback to no-ops (same pattern as app.py)
try:
    from scripts.crypto import enc, dec, node_hash
except ImportError:
    from crypto import enc, dec, node_hash  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def load_env(path: str = ".env") -> None:
    if load_dotenv:
        load_dotenv(path)


def env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


# -----------------------------------------------------------------------------
# Config helpers
# -----------------------------------------------------------------------------

def _llm_model() -> str:
    return os.getenv("LLM_MODEL", "groq/llama-3.3-70b-versatile")


def _llm_fast() -> str:
    return os.getenv("LLM_FAST", "groq/qwen3-32b")


def _embedding_model() -> Optional[str]:
    return os.getenv("EMBEDDING_MODEL") or None


def _now_iso() -> str:
    return _iso(datetime.now(timezone.utc))


def _default_llm_fn(messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: Optional[int] = None, **kw):
    """Default LLM caller using litellm. Accepts the same signature app.py uses."""
    model = os.getenv("LLM_FAST", _llm_fast())
    kwargs: Dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    kwargs.update(kw)
    return litellm.completion(**kwargs)


def _default_embed_fn(texts: List[str]) -> List[List[float]]:
    """Default embedding caller using litellm. Returns list of vectors."""
    model = _embedding_model()
    if not model:
        return []
    try:
        resp = litellm.embedding(model=model, input=texts)
        # litellm returns data sorted by index; be defensive.
        items = sorted(resp.data, key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in items]
    except Exception as e:
        print(f"[graph_memory] embedding failed: {e}")
        return []


# -----------------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------------

class Entity:
    def __init__(
        self,
        name: str,
        entity_type: str = "",
        summary: str = "",
        entity_uuid: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ):
        self.uuid = entity_uuid or str(__import__("uuid").uuid4())
        self.name = name.strip()
        self.entity_type = entity_type.strip() or "Entity"
        self.summary = summary.strip()
        self.embedding = embedding

    def __repr__(self) -> str:
        return f"Entity({self.name!r})"


class Fact:
    def __init__(
        self,
        source: "Entity",
        target: "Entity",
        relation_type: str,
        fact: str,
        fact_uuid: Optional[str] = None,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        created_at: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ):
        self.uuid = fact_uuid or str(__import__("uuid").uuid4())
        self.source = source
        self.target = target
        self.relation_type = relation_type.strip().upper().replace(" ", "_")
        self.fact = fact.strip()
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.created_at = created_at or _now_iso()
        self.embedding = embedding

    def __repr__(self) -> str:
        return f"Fact({self.source.name} -[{self.relation_type}]-> {self.target.name})"


# -----------------------------------------------------------------------------
# Prompts
# -----------------------------------------------------------------------------

_ENTITY_EXTRACTION_PROMPT = """You are a knowledge-graph extraction engine.

Extract semantic entities from the CURRENT MESSAGE of a conversation.
Entities are people, organizations, skills, projects, goals, values, beliefs,
constraints, places, technologies, or any concrete concept worth remembering.

Rules:
1. ALWAYS extract the USER/speaker as the first entity if they say something
   about themselves. Use a canonical name like "User" or the provided name.
2. Be specific and use full names when possible.
3. Do NOT extract relationships or actions as entities.
4. Do NOT extract temporal information (dates, times) as entities.
5. Each entity must be a real-world concept that could be linked to others.

Return ONLY a JSON list of objects:
[
  {"name": "...", "type": "Person|Organization|Skill|Project|Goal|Value|Belief|Constraint|Place|Technology|Other", "summary": "1-sentence description"},
  ...
]
"""

_ENTITY_RESOLUTION_PROMPT = """You are resolving whether a newly extracted entity
is the same real-world entity as one already stored in the knowledge graph.

NEW ENTITY:
Name: {new_name}
Type: {new_type}
Summary: {new_summary}

EXISTING ENTITIES:
{existing}

Task:
1. If the NEW ENTITY matches one of the EXISTING ENTITIES, return JSON:
   {{"is_duplicate": true, "uuid": "<existing uuid>", "name": "<best full name>"}}
2. Otherwise return:
   {{"is_duplicate": false}}

Guidelines:
- Two entities are duplicates if they refer to the same real-world thing,
  even if the names differ slightly ("Python" vs "the Python language").
- Prefer the most complete canonical name when returning a duplicate.
- Return ONLY the JSON object, no explanation.
"""

_FACT_EXTRACTION_PROMPT = """You are a fact-extraction engine for a knowledge graph.

Given the conversation and a list of entities, extract factual relationships
(links) between pairs of entities mentioned in the CURRENT MESSAGE.

Rules:
1. Extract facts ONLY between DISTINCT entities from the provided list.
2. Use a concise, all-caps relation_type like LOVES, WORKS_FOR, LOCATED_IN,
   KNOWS, BUILT, HAS_GOAL, VALUES, etc.
3. The `fact` field should be a natural-language sentence capturing the
   relationship and any relevant detail.
4. Consider temporal aspects (e.g., "started", "moved", "quit"). If a fact
   has a time boundary, include it in the fact text.
5. Do not invent entities not in the list.
6. If a fact contradicts an earlier state, still extract it as a new fact.

Return ONLY a JSON list:
[
  {"source": "<entity name>", "target": "<entity name>", "relation_type": "...", "fact": "...", "temporal": "optional temporal phrase"},
  ...
]

If no facts relate the entities, return [].
"""

_FACT_RESOLUTION_PROMPT = """You are resolving whether a newly extracted fact
contradicts or duplicates an existing fact between the same two entities.

NEW FACT (valid from {new_valid_from} to {new_valid_to}):
{new_fact}

EXISTING FACTS:
{existing}

Task:
Return JSON with one of these decisions:
- {{"decision": "duplicate", "uuid": "<existing uuid>"}}  — same core information, possibly with different wording.
- {{"decision": "contradiction", "uuid": "<existing uuid>"}} — the new fact makes the old fact no longer true within an overlapping time window.
- {{"decision": "new"}} — unrelated or additional information.

Guidelines:
- Facts don't need identical wording to be duplicates; they must express the
  same core information.
- A contradiction only applies when the two facts describe the same state at
  overlapping times. "I lived in Paris until 2020" does NOT contradict
  "I live in Berlin now" because the time windows do not overlap.
- "I used to work at Google" contradicts "I work at Google now" because the
  current-time windows overlap.
- "I know Python" and "I am fluent in Python" are duplicates.
- "I work at Google" and "I work at Microsoft" are contradictions if both are
  claimed to be currently true.
- Return ONLY the JSON object, no explanation.
"""

_TEMPORAL_EXTRACTION_PROMPT = """Extract temporal information from the following
fact extracted from a conversation.

Reference time (when the message was sent): {ref_time}

Fact: {fact}

Return ONLY a JSON object with optional fields:
{{
  "valid_from": "ISO-8601 datetime or null",
  "valid_to": "ISO-8601 datetime or null"
}}

Interpret relative phrases like "two weeks ago", "next Thursday", "since 2020",
"last summer" relative to the reference time. If the fact is negated or past tense
(e.g. "I used to work at X", "I no longer use Y"), set valid_to to the reference time.
If no time is mentioned and the fact is not negated/past tense, return nulls.
"""


# -----------------------------------------------------------------------------
# Extraction helpers
# -----------------------------------------------------------------------------

def _extract_json(text: str) -> Any:
    """Extract the first JSON object/array from an LLM response."""
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    # Find first { or [
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        end = _find_matching(text, start_arr, "[", "]")
        if end != -1:
            return json.loads(text[start_arr:end + 1])
    if start_obj != -1:
        end = _find_matching(text, start_obj, "{", "}")
        if end != -1:
            return json.loads(text[start_obj:end + 1])
    return json.loads(text)


def _find_matching(text: str, start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not in_str:
            in_str = True
            continue
        if ch == '"' and in_str:
            in_str = False
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_entities(
    current_message: str,
    previous_messages: str = "",
    llm_fn: Optional[Callable] = None,
) -> List[Entity]:
    """Extract entities from the current message with optional prior context."""
    if llm_fn is None:
        llm_fn = _default_llm_fn

    content = f"<PREVIOUS_MESSAGES>\n{previous_messages}\n</PREVIOUS_MESSAGES>\n\n"
    content += f"<CURRENT_MESSAGE>\n{current_message}\n</CURRENT_MESSAGE>"

    resp = llm_fn(
        messages=[
            {"role": "system", "content": _ENTITY_EXTRACTION_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or "[]"
    data = _extract_json(raw)
    if not isinstance(data, list):
        return []

    entities: List[Entity] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip()
        if not name:
            continue
        entities.append(Entity(
            name=name,
            entity_type=item.get("type", "Other"),
            summary=item.get("summary", ""),
        ))
    return entities


def extract_facts(
    entities: List[Entity],
    current_message: str,
    previous_messages: str = "",
    llm_fn: Optional[Callable] = None,
) -> List[Fact]:
    """Extract facts (edges) between the provided entities."""
    if llm_fn is None:
        llm_fn = _default_llm_fn

    entity_block = "\n".join(
        f"- {e.name} ({e.entity_type}): {e.summary}" for e in entities
    )
    content = (
        f"<ENTITIES>\n{entity_block}\n</ENTITIES>\n\n"
        f"<PREVIOUS_MESSAGES>\n{previous_messages}\n</PREVIOUS_MESSAGES>\n\n"
        f"<CURRENT_MESSAGE>\n{current_message}\n</CURRENT_MESSAGE>"
    )

    resp = llm_fn(
        messages=[
            {"role": "system", "content": _FACT_EXTRACTION_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or "[]"
    data = _extract_json(raw)
    if not isinstance(data, list):
        return []

    entity_by_name = {e.name: e for e in entities}
    facts: List[Fact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        source_name = item.get("source", "").strip()
        target_name = item.get("target", "").strip()
        relation_type = item.get("relation_type", "RELATED_TO").strip()
        fact_text = item.get("fact", "").strip()
        if not source_name or not target_name or not fact_text:
            continue
        source = entity_by_name.get(source_name)
        target = entity_by_name.get(target_name)
        if source is None or target is None:
            continue
        facts.append(Fact(
            source=source,
            target=target,
            relation_type=relation_type,
            fact=fact_text,
            valid_from=None,
            valid_to=None,
        ))
    return facts


def resolve_entities(
    new_entities: List[Entity],
    existing_entities: List[Dict[str, Any]],
    llm_fn: Optional[Callable] = None,
) -> Tuple[List[Entity], Dict[str, str]]:
    """Return (merged_entities, new_to_existing_uuid_map).

    existing_entities should be a list of dicts with keys:
      uuid, name, type, summary, embedding (optional).
    """
    if llm_fn is None:
        llm_fn = _default_llm_fn

    merged: List[Entity] = []
    mapping: Dict[str, str] = {}  # new entity uuid -> existing uuid

    for new in new_entities:
        # Quick candidate filtering by embedding similarity if available.
        candidates = _candidate_entities(new, existing_entities)
        if not candidates:
            merged.append(new)
            continue

        candidate_block = "\n".join(
            f"- UUID: {c['uuid']}\n  Name: {c.get('name', '')}\n  Type: {c.get('type', '')}\n  Summary: {c.get('summary', '')}"
            for c in candidates[:5]
        )
        prompt = _ENTITY_RESOLUTION_PROMPT.format(
            new_name=new.name,
            new_type=new.entity_type,
            new_summary=new.summary,
            existing=candidate_block,
        )
        resp = llm_fn(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            decision = _extract_json(raw)
        except Exception:
            decision = {"is_duplicate": False}

        if decision.get("is_duplicate"):
            existing_uuid = decision.get("uuid")
            if existing_uuid:
                new.uuid = existing_uuid
                mapping[new.uuid] = existing_uuid
                # Optionally adopt the canonical name.
                canonical = decision.get("name", new.name)
                new.name = canonical
                merged.append(new)
                continue
        merged.append(new)

    return merged, mapping


def _candidate_entities(
    new_entity: Entity,
    existing_entities: List[Dict[str, Any]],
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """Pick likely duplicate candidates by token overlap or embedding similarity."""
    new_tokens = set(_tokens(new_entity.name + " " + new_entity.summary))
    scored = []
    for ex in existing_entities:
        ex_tokens = set(_tokens(str(ex.get("name", "")) + " " + str(ex.get("summary", ""))))
        if not new_tokens or not ex_tokens:
            score = 0.0
        else:
            score = len(new_tokens & ex_tokens) / max(len(new_tokens), len(ex_tokens))
        # embedding similarity bonus
        if new_entity.embedding and ex.get("embedding"):
            try:
                emb_sim = _cosine_similarity(new_entity.embedding, ex["embedding"])
                score = max(score, emb_sim * 0.8)  # blend
            except Exception:
                pass
        if score > 0.05:
            scored.append((score, ex))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for _, ex in scored[:top_k]]


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text) if len(t) > 2]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# -----------------------------------------------------------------------------
# Temporal extraction
# -----------------------------------------------------------------------------

# True past-tense facts describe a state that ended in the past (e.g. "used to
# work at X"). They are valid up to the reference time.
_PAST_FACT_PATTERNS = [
    re.compile(r"\bused?\s+to\b", re.I),
    re.compile(r"\bformerly?\b", re.I),
    re.compile(r"\bformer\b", re.I),
    re.compile(r"\bex[-\s]?", re.I),
]

# Negation facts state that something is no longer true right now (e.g. "no
# longer works at X"). They are valid from the reference time onward and usually
# contradict an existing positive fact.
_NEGATION_FACT_PATTERNS = [
    re.compile(r"\bno\s+longer\b", re.I),
    re.compile(r"\bstopped\s+(?:doing|using|working|living|going|being|smoking|drinking)\b", re.I),
    re.compile(r"\bquit\b", re.I),
    re.compile(r"\bgave\s+up\b", re.I),
    re.compile(r"\bdon't\s+(?:work|live|use|do)\s+(?:at|for|in|there|anymore)\b", re.I),
    re.compile(r"\bdid\s+not\s+(?:work|live|use|do)\b", re.I),
]

_VALID_FROM_KEYWORDS = [
    "since", "from", "starting", "started", "began", "begins", "begun",
    "joined", "adopted", "launched", "created",
]

_VALID_TO_KEYWORDS = [
    "until", "till", "by", "before", "ending", "ended",
]

# Phrases like "valid to 2025", "good until Friday" mark an end bound even when
# a bare "to" would otherwise be ambiguous.
_END_BOUND_PHRASES = [
    re.compile(r"\b(?:valid|good|available|open)\s+(?:to|until|till)\b", re.I),
]


def _iso(dt: datetime) -> str:
    """Return a UTC ISO-8601 string for a datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_past_fact(text: str) -> bool:
    """Return True when the fact describes a state that ended in the past."""
    return any(p.search(text) for p in _PAST_FACT_PATTERNS)


def _is_negation_fact(text: str) -> bool:
    """Return True when the fact states something is no longer true right now."""
    return any(p.search(text) for p in _NEGATION_FACT_PATTERNS)


def _parse_year(year: int, side: Optional[str]) -> datetime:
    """Return a reasonable date for a bare year."""
    month = 12 if side == "to" else 1
    day = 31 if side == "to" else 1
    return datetime(year, month, day, tzinfo=timezone.utc)


def _parse_date(text: str, ref_time: datetime) -> Optional[datetime]:
    """Try parsedatetime; return a UTC datetime or None."""
    cal = pdt.Calendar()
    parsed, status = cal.parseDT(text, sourceTime=ref_time)
    if status == 0:
        return None

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))
        # parsedatetime sometimes interprets a bare year as a time-of-day
        # (e.g. "2021" -> 20:21 on the reference date). Detect that case and
        # use the year directly instead.
        if (status == 2 or
            (parsed.year == ref_time.year and
             parsed.month == ref_time.month and
             parsed.day == ref_time.day)):
            side = _temporal_keyword_side(text)
            return _parse_year(year, side)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _parse_date_range(text: str, ref_time: datetime) -> Tuple[Optional[str], Optional[str]]:
    """Try to extract a start/end year pair from phrases like 'from X to Y'."""
    # Match patterns like: from 2020 to 2022, since 2021 until 2023, 2020-2022
    m = re.search(
        r"(?:\bfrom\b|\bsince\b)?\s*\b(19\d{2}|20\d{2})\b\s*"
        r"(?:to|until|till|through|[-–])\s*"
        r"\b(19\d{2}|20\d{2})\b",
        text,
        re.I,
    )
    if m:
        start_year, end_year = int(m.group(1)), int(m.group(2))
        return _iso(_parse_year(start_year, "from")), _iso(_parse_year(end_year, "to"))
    return None, None


def _temporal_keyword_side(text: str) -> Optional[str]:
    """Determine whether a detected date is a start or end bound.

    Returns 'from', 'to', or None if the text is ambiguous.
    """
    lowered = text.lower()
    from_score = sum(1 for kw in _VALID_FROM_KEYWORDS if f" {kw} " in f" {lowered} ")
    to_score = sum(1 for kw in _VALID_TO_KEYWORDS if f" {kw} " in f" {lowered} ")
    if any(p.search(text) for p in _END_BOUND_PHRASES):
        to_score += 1
    if from_score and not to_score:
        return "from"
    if to_score and not from_score:
        return "to"
    return None


def extract_temporal(
    fact_text: str,
    ref_time: Optional[datetime] = None,
    llm_fn: Optional[Callable] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (valid_from, valid_to) ISO strings for a fact.

    Uses a hybrid approach: parsedatetime for clear cases, with an LLM fallback
    for ambiguous or missing temporal information. Past-tense/negated facts are
    treated as valid only up to the reference time.
    """
    ref_time = ref_time or datetime.now(timezone.utc)

    # Past-tense facts describe a state that ended in the past.
    if _is_past_fact(fact_text):
        return None, _iso(ref_time)

    # Try explicit year ranges first (e.g. "from 2020 to 2022").  Even negated
    # facts can carry a start date.
    vf, vt = _parse_date_range(fact_text, ref_time)
    if vf or vt:
        return vf, vt

    # Try the fast rule-based parser for a single date.
    parsed = _parse_date(fact_text, ref_time)

    # Past-tense facts describe a state that ended in the past.
    if _is_past_fact(fact_text):
        return None, _iso(parsed if parsed else ref_time)

    # Negation facts state something is no longer true right now; they are valid
    # from the detected date (or the reference time) onward.
    if _is_negation_fact(fact_text):
        return _iso(parsed if parsed else ref_time), None

    if parsed:
        side = _temporal_keyword_side(fact_text)
        iso = _iso(parsed)
        if side == "to":
            return None, iso
        # Default to a start bound for any detected date.
        return iso, None

    # Fallback to LLM for fuzzy phrases parsedatetime missed.
    if llm_fn is None:
        llm_fn = _default_llm_fn
    prompt = _TEMPORAL_EXTRACTION_PROMPT.format(
        ref_time=_iso(ref_time),
        fact=fact_text,
    )
    try:
        resp = llm_fn(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or "{}"
        data = _extract_json(raw)
    except Exception:
        data = {}
    valid_from = data.get("valid_from") or None
    valid_to = data.get("valid_to") or None
    return valid_from, valid_to


# -----------------------------------------------------------------------------
# Graph I/O
# -----------------------------------------------------------------------------

def get_driver() -> Any:
    """Convenience driver factory."""
    uri = env_var("NEO4J_URI")
    user = env_var("NEO4J_USER")
    password = env_var("NEO4J_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")


def fetch_existing_entities(
    driver,
    database: str,
    person_id: str,
) -> List[Dict[str, Any]]:
    """Fetch all :Entity nodes for a person with decrypted names/summaries."""
    query = """
    MATCH (e:Entity {person_id: $person_id})
    RETURN e.uuid AS uuid,
           e.name AS name_enc,
           e.type AS type_enc,
           e.summary AS summary_enc,
           e.embedding AS embedding
    """
    with driver.session(database=database) as session:
        rows = session.run(query, person_id=person_id).data()
    for row in rows:
        row["name"] = dec(row.get("name_enc") or "", person_id)
        row["type"] = dec(row.get("type_enc") or "", person_id)
        row["summary"] = dec(row.get("summary_enc") or "", person_id)
    return rows


def fetch_facts_between(
    driver,
    database: str,
    person_id: str,
    source_uuid: str,
    target_uuid: str,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch currently valid, non-expired facts between two entity UUIDs."""
    now = _iso(current_time or datetime.now(timezone.utc))
    query = """
    MATCH (a:Entity {uuid: $source_uuid, person_id: $person_id})-
          [f:FACT {person_id: $person_id}]->(b:Entity {uuid: $target_uuid, person_id: $person_id})
    WHERE f.expired_at IS NULL
      AND (f.valid_from IS NULL OR f.valid_from <= $now)
      AND (f.valid_to IS NULL OR f.valid_to >= $now)
    RETURN f.uuid AS uuid,
           f.fact AS fact_enc,
           f.relation_type AS relation_type,
           f.valid_from AS valid_from,
           f.valid_to AS valid_to
    """
    with driver.session(database=database) as session:
        rows = session.run(
            query,
            person_id=person_id,
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            now=now,
        ).data()
    for row in rows:
        row["fact"] = dec(row.get("fact_enc") or "", person_id)
    return rows


def ensure_indexes(driver, database: str) -> None:
    """Create required indexes/constraints for the ERF graph."""
    statements = [
        "CREATE CONSTRAINT entity_uuid IF NOT EXISTS FOR (e:Entity) REQUIRE e.uuid IS UNIQUE",
        "CREATE CONSTRAINT episode_uuid IF NOT EXISTS FOR (ep:Episode) REQUIRE ep.id IS UNIQUE",
        "CREATE INDEX entity_person_id IF NOT EXISTS FOR (e:Entity) ON (e.person_id)",
        "CREATE INDEX fact_uuid IF NOT EXISTS FOR ()-[f:FACT]-() ON (f.uuid)",
        "CREATE INDEX fact_person_id IF NOT EXISTS FOR ()-[f:FACT]-() ON (f.person_id)",
        "CREATE INDEX entity_mention_episode IF NOT EXISTS FOR ()-[m:MENTIONED_IN]-() ON (m.person_id)",
    ]
    with driver.session(database=database) as session:
        for stmt in statements:
            try:
                session.run(stmt)
            except Exception as e:
                print(f"[ensure_indexes] {stmt} failed: {e}")


def _embedding_property(embedding: Optional[List[float]]) -> Optional[List[float]]:
    """Truncate huge embedding lists? Neo4j handles list<float> fine."""
    return embedding if embedding else None


def create_or_update_entity(
    driver,
    database: str,
    person_id: str,
    entity: Entity,
    episode_id: Optional[str] = None,
) -> None:
    """Write or merge an Entity node, linking it to a Person and optionally Episode."""
    query = """
    MERGE (p:Person {id: $person_id})
    MERGE (e:Entity {uuid: $uuid, person_id: $person_id})
    SET e.name = $name_enc,
        e.type = $type_enc,
        e.summary = $summary_enc,
        e.name_hash = $name_hash,
        e.embedding = $embedding,
        e.created_at = coalesce(e.created_at, $now)
    MERGE (p)-[:HAS_ENTITY]->(e)
    """
    if episode_id:
        query += """
    WITH e
    MATCH (ep:Episode {id: $episode_id, person_id: $person_id})
    MERGE (e)-[:MENTIONED_IN]->(ep)
    """
    with driver.session(database=database) as session:
        session.run(
            query,
            person_id=person_id,
            uuid=entity.uuid,
            name_enc=enc(entity.name, person_id),
            type_enc=enc(entity.entity_type, person_id),
            summary_enc=enc(entity.summary, person_id),
            name_hash=node_hash(entity.name, person_id),
            embedding=_embedding_property(entity.embedding),
            now=_now_iso(),
            episode_id=episode_id,
        )


def create_fact(
    driver,
    database: str,
    person_id: str,
    fact: Fact,
    episode_id: Optional[str] = None,
) -> None:
    """Write a FACT relationship between two existing entities."""
    query = """
    MATCH (a:Entity {uuid: $source_uuid, person_id: $person_id})
    MATCH (b:Entity {uuid: $target_uuid, person_id: $person_id})
    CREATE (a)-[f:FACT {
        uuid: $uuid,
        person_id: $person_id,
        fact: $fact_enc,
        relation_type: $relation_type,
        valid_from: $valid_from,
        valid_to: $valid_to,
        created_at: $created_at,
        embedding: $embedding
    }]->(b)
    """
    if episode_id:
        query += """
    WITH f
    MATCH (ep:Episode {id: $episode_id, person_id: $person_id})
    SET f.source_episode_id = $episode_id
    MERGE (ep)-[:EXTRACTED]->(a)
    MERGE (ep)-[:EXTRACTED]->(b)
    """
    # Untimed facts are valid from the moment they are recorded.
    created_at = fact.created_at or _now_iso()
    valid_from = fact.valid_from or created_at
    with driver.session(database=database) as session:
        session.run(
            query,
            person_id=person_id,
            source_uuid=fact.source.uuid,
            target_uuid=fact.target.uuid,
            uuid=fact.uuid,
            fact_enc=enc(fact.fact, person_id),
            relation_type=fact.relation_type,
            valid_from=valid_from,
            valid_to=fact.valid_to,
            created_at=created_at,
            embedding=_embedding_property(fact.embedding),
            episode_id=episode_id,
        )


def expire_fact(
    driver,
    database: str,
    person_id: str,
    fact_uuid: str,
    expired_at: Optional[str] = None,
    valid_to: Optional[str] = None,
) -> None:
    """Mark an existing FACT relationship as expired (contradicted).

    Sets both `expired_at` (transaction time) and `valid_to` (validity end time)
    so retrieval can hide facts that are no longer true.
    """
    query = """
    MATCH (:Entity {person_id: $person_id})-[f:FACT {uuid: $uuid, person_id: $person_id}]->(:Entity {person_id: $person_id})
    SET f.expired_at = $expired_at,
        f.valid_to = coalesce($valid_to, f.valid_to, $expired_at)
    """
    now = expired_at or _now_iso()
    with driver.session(database=database) as session:
        session.run(
            query,
            person_id=person_id,
            uuid=fact_uuid,
            expired_at=now,
            valid_to=valid_to,
        )


def _parse_iso_or_none(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string to a UTC datetime, or return None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _facts_temporally_overlap(
    new_valid_from: Optional[str],
    new_valid_to: Optional[str],
    old_valid_from: Optional[str],
    old_valid_to: Optional[str],
) -> bool:
    """Return True if two validity intervals could describe the same state."""
    # Unbounded facts overlap with everything.
    if (new_valid_from is None and new_valid_to is None) or (
        old_valid_from is None and old_valid_to is None
    ):
        return True
    nf = _parse_iso_or_none(new_valid_from)
    nt = _parse_iso_or_none(new_valid_to)
    of = _parse_iso_or_none(old_valid_from)
    ot = _parse_iso_or_none(old_valid_to)

    # Treat missing bounds as +/- infinity.
    start_a = nf or datetime.min.replace(tzinfo=timezone.utc)
    end_a = nt or datetime.max.replace(tzinfo=timezone.utc)
    start_b = of or datetime.min.replace(tzinfo=timezone.utc)
    end_b = ot or datetime.max.replace(tzinfo=timezone.utc)
    return start_a <= end_b and start_b <= end_a


_NEGATION_WORDS = {
    "no longer", "quit", "quits", "quitting", "quit", "resigned", "resigns",
    "resigning", "stopped", "stops", "stopping", "ceased", "ceases",
    "ceasing", "gave up", "gives up", "giving up",
}


def _is_heuristic_contradiction(new_fact: Fact, old_fact: Dict[str, Any]) -> bool:
    """Fast, rule-based contradiction detection before calling the LLM."""
    new_text = f"{new_fact.relation_type} {new_fact.fact}".lower()
    old_text = f"{old_fact.get('relation_type', '')} {old_fact.get('fact', '')}".lower()

    # Negation of an existing positive fact is a contradiction.
    has_negation = any(w in new_text for w in _NEGATION_WORDS)
    if has_negation:
        # Ensure the old fact is a positive statement about the same relation.
        old_is_positive = not any(w in old_text for w in _NEGATION_WORDS)
        if old_is_positive:
            return True

    # Mutually exclusive location/employer values for the same relation.
    # Example: "lives in Paris" vs "lives in Berlin".
    exclusive_relations = {"lives_in", "works_for", "located_in", "works_at"}
    if new_fact.relation_type.upper() in exclusive_relations:
        # Very naive check: same relation, different object names.
        # A real check would compare entities; the LLM handles nuance.
        return False  # keep LLM in the loop for safety

    return False


def _is_heuristic_duplicate(new_fact: Fact, old_fact: Dict[str, Any]) -> bool:
    """Fast, rule-based duplicate detection."""
    if new_fact.relation_type.upper() != (old_fact.get("relation_type") or "").upper():
        return False
    new_text = new_fact.fact.lower()
    old_text = (old_fact.get("fact") or "").lower()
    if new_text == old_text:
        return True
    # High token overlap for short facts.
    new_tokens = set(_tokens(new_text))
    old_tokens = set(_tokens(old_text))
    if not new_tokens or not old_tokens:
        return False
    overlap = len(new_tokens & old_tokens) / max(len(new_tokens), len(old_tokens))
    return overlap >= 0.9


def resolve_facts(
    driver,
    database: str,
    person_id: str,
    facts: List[Fact],
    llm_fn: Optional[Callable] = None,
) -> List[Fact]:
    """For each new fact, detect duplicates/contradictions with existing facts.

    Returns the list of facts that should be written (duplicates are dropped,
    contradictions cause the old fact to be expired).
    """
    if llm_fn is None:
        llm_fn = _default_llm_fn

    facts_to_write: List[Fact] = []
    for fact in facts:
        existing = fetch_facts_between(
            driver, database, person_id, fact.source.uuid, fact.target.uuid
        )
        existing += fetch_facts_between(
            driver, database, person_id, fact.target.uuid, fact.source.uuid
        )

        # A fact can only contradict another if their validity windows overlap.
        candidates = [
            ex for ex in existing
            if _facts_temporally_overlap(
                fact.valid_from, fact.valid_to,
                ex.get("valid_from"), ex.get("valid_to"),
            )
        ]

        if not candidates:
            facts_to_write.append(fact)
            continue

        decision: Optional[Dict[str, Any]] = None
        # 1. Fast heuristic path.
        for ex in candidates:
            if _is_heuristic_duplicate(fact, ex):
                decision = {"decision": "duplicate", "uuid": ex["uuid"]}
                break
            if _is_heuristic_contradiction(fact, ex):
                decision = {"decision": "contradiction", "uuid": ex["uuid"]}
                break

        # 2. LLM fallback for ambiguous cases.
        if decision is None:
            existing_block = "\n".join(
                f"- UUID: {ex['uuid']}\n"
                f"  Relation: {ex.get('relation_type', 'RELATED_TO')}\n"
                f"  Validity: {ex.get('valid_from') or '...'} to {ex.get('valid_to') or '...'}\n"
                f"  Fact: {ex['fact']}"
                for ex in candidates[:10]
            )
            prompt = _FACT_RESOLUTION_PROMPT.format(
                new_fact=f"{fact.source.name} -[{fact.relation_type}]-> {fact.target.name}: {fact.fact}",
                new_valid_from=fact.valid_from or "unspecified",
                new_valid_to=fact.valid_to or "unspecified",
                existing=existing_block,
            )
            try:
                resp = llm_fn(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                )
                raw = resp.choices[0].message.content or "{}"
                decision = _extract_json(raw)
            except Exception:
                decision = {"decision": "new"}

        decision_type = decision.get("decision", "new") if decision else "new"
        if decision_type == "duplicate":
            continue
        if decision_type == "contradiction":
            old_uuid = decision.get("uuid")
            if old_uuid:
                # The old fact stopped being true at the moment the new fact
                # became valid (or when it was created if no explicit time).
                contradiction_valid_to = fact.valid_from or fact.created_at
                expire_fact(
                    driver,
                    database,
                    person_id,
                    old_uuid,
                    valid_to=contradiction_valid_to,
                )
        facts_to_write.append(fact)

    return facts_to_write


# -----------------------------------------------------------------------------
# High-level pipeline
# -----------------------------------------------------------------------------

def run_graph_pipeline(
    conversation: str,
    person_id: str,
    driver,
    database: str,
    ref_time: Optional[datetime] = None,
    episode_id: Optional[str] = None,
    llm_fn: Optional[Callable] = None,
    embed_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Run the full Zep-style ERF extraction pipeline.

    Args:
        conversation: the message text to process.
        person_id: the user's stable id.
        driver: Neo4j driver.
        database: Neo4j database name.
        ref_time: optional reference time for temporal extraction.
        episode_id: optional existing episode to link entities/facts to.
        llm_fn: optional LLM caller.
        embed_fn: optional embedding caller (texts -> list of vectors).

    Returns:
        Dict with created/updated entity uuids and fact uuids.
    """
    if llm_fn is None:
        llm_fn = _default_llm_fn
    if embed_fn is None:
        embed_fn = _default_embed_fn

    # 1. Extract entities.
    entities = extract_entities(conversation, llm_fn=llm_fn)
    if not entities:
        return {"entities": [], "facts": [], "episode_id": episode_id}

    # 2. Resolve against existing entities.
    existing_entities = fetch_existing_entities(driver, database, person_id)
    merged_entities, _ = resolve_entities(entities, existing_entities, llm_fn=llm_fn)

    # 3. Compute embeddings for entities.
    if _embedding_model():
        entity_texts = [f"{e.name} {e.entity_type} {e.summary}" for e in merged_entities]
        entity_embs = embed_fn(entity_texts)
        for e, emb in zip(merged_entities, entity_embs):
            e.embedding = emb

    # 4. Extract facts.
    facts = extract_facts(merged_entities, conversation, llm_fn=llm_fn)

    # 5. Extract temporal bounds for facts.
    ref_time = ref_time or datetime.now(timezone.utc)
    for fact in facts:
        try:
            valid_from, valid_to = extract_temporal(fact.fact, ref_time, llm_fn=llm_fn)
            fact.valid_from = valid_from
            fact.valid_to = valid_to
        except Exception:
            pass

    # 6. Compute embeddings for facts.
    if _embedding_model() and facts:
        fact_texts = [f.fact for f in facts]
        fact_embs = embed_fn(fact_texts)
        for f, emb in zip(facts, fact_embs):
            f.embedding = emb

    # 7. Resolve facts (duplicates + contradictions).
    facts_to_write = resolve_facts(driver, database, person_id, facts, llm_fn=llm_fn)

    # 8. Write entities.
    for entity in merged_entities:
        create_or_update_entity(driver, database, person_id, entity, episode_id=episode_id)

    # 9. Write facts.
    for fact in facts_to_write:
        create_fact(driver, database, person_id, fact, episode_id=episode_id)

    return {
        "entities": [
            {"uuid": e.uuid, "name": e.name, "type": e.entity_type}
            for e in merged_entities
        ],
        "facts": [
            {"uuid": f.uuid, "fact": f.fact, "relation_type": f.relation_type}
            for f in facts_to_write
        ],
        "episode_id": episode_id,
    }


# -----------------------------------------------------------------------------
# Retrieval
# -----------------------------------------------------------------------------

def search_facts(
    driver,
    database: str,
    person_id: str,
    query_text: str,
    top_k: int = 10,
    embed_fn: Optional[Callable] = None,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Hybrid fact retrieval: vector + BM25 fallback + recency.

    Only returns facts that are currently valid: valid_from <= now and
    (valid_to IS NULL OR valid_to >= now).
    """
    if embed_fn is None:
        embed_fn = _default_embed_fn

    now = _iso(current_time or datetime.now(timezone.utc))
    query_embedding: Optional[List[float]] = None
    if _embedding_model():
        embs = embed_fn([query_text])
        query_embedding = embs[0] if embs else None

    cypher = """
    MATCH (a:Entity {person_id: $person_id})-[f:FACT {person_id: $person_id}]->(b:Entity {person_id: $person_id})
    WHERE f.expired_at IS NULL
      AND (f.valid_from IS NULL OR f.valid_from <= $now)
      AND (f.valid_to IS NULL OR f.valid_to >= $now)
    RETURN a.uuid AS source_uuid,
           b.uuid AS target_uuid,
           a.name AS source_name_enc,
           b.name AS target_name_enc,
           f.uuid AS uuid,
           f.fact AS fact_enc,
           f.relation_type AS relation_type,
           f.valid_from AS valid_from,
           f.valid_to AS valid_to,
           f.created_at AS created_at,
           f.embedding AS embedding
    """
    with driver.session(database=database) as session:
        rows = session.run(cypher, person_id=person_id, now=now).data()

    query_tokens = set(_tokens(query_text))
    scored = []
    for row in rows:
        fact_text = dec(row.get("fact_enc") or "", person_id)
        source_name = dec(row.get("source_name_enc") or "", person_id)
        target_name = dec(row.get("target_name_enc") or "", person_id)
        full_text = f"{source_name} {target_name} {fact_text}"

        # BM25-ish token overlap
        fact_tokens = set(_tokens(full_text))
        overlap = len(query_tokens & fact_tokens) / max(len(query_tokens), 1)

        # Vector similarity
        emb_sim = 0.0
        if query_embedding and row.get("embedding"):
            try:
                emb_sim = _cosine_similarity(query_embedding, row["embedding"])
            except Exception:
                pass

        score = 0.6 * emb_sim + 0.4 * overlap
        if score > 0.02:
            item = {
                **row,
                "fact": fact_text,
                "source_name": source_name,
                "target_name": target_name,
                "score": score,
            }
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]


def bfs_expand(
    driver,
    database: str,
    person_id: str,
    seed_entity_uuids: List[str],
    depth: int = 2,
    top_k: int = 20,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Breadth-first expansion from seed entities to find related facts.

    Only returns currently valid facts.
    """
    now = _iso(current_time or datetime.now(timezone.utc))
    # Neo4j does not accept parameters for variable-length path bounds, so we
    # interpolate the integer depth safely into the query string.
    query = f"""
    MATCH path = (seed:Entity {{person_id: $person_id}})-[:FACT*1..{depth}]->(related:Entity {{person_id: $person_id}})
    WHERE seed.uuid IN $seed_uuids
    UNWIND relationships(path) AS f
    MATCH (a)-[f]->(b)
    WHERE f.expired_at IS NULL
      AND (f.valid_from IS NULL OR f.valid_from <= $now)
      AND (f.valid_to IS NULL OR f.valid_to >= $now)
    RETURN DISTINCT a.uuid AS source_uuid,
           b.uuid AS target_uuid,
           a.name AS source_name_enc,
           b.name AS target_name_enc,
           f.uuid AS uuid,
           f.fact AS fact_enc,
           f.relation_type AS relation_type,
           f.valid_from AS valid_from,
           f.valid_to AS valid_to,
           length(path) AS hop
    ORDER BY hop
    LIMIT $top_k
    """
    with driver.session(database=database) as session:
        rows = session.run(
            query,
            person_id=person_id,
            seed_uuids=seed_entity_uuids,
            top_k=top_k,
            now=now,
        ).data()

    for row in rows:
        row["fact"] = dec(row.get("fact_enc") or "", person_id)
        row["source_name"] = dec(row.get("source_name_enc") or "", person_id)
        row["target_name"] = dec(row.get("target_name_enc") or "", person_id)
    return rows


def fetch_all_facts(
    driver,
    database: str,
    person_id: str,
    limit: int = 10000,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch all non-expired, currently valid facts for a person, ordered by recency."""
    now = _iso(current_time or datetime.now(timezone.utc))
    query = """
    MATCH (a:Entity {person_id: $person_id})-[f:FACT {person_id: $person_id}]->(b:Entity {person_id: $person_id})
    WHERE f.expired_at IS NULL
      AND (f.valid_from IS NULL OR f.valid_from <= $now)
      AND (f.valid_to IS NULL OR f.valid_to >= $now)
    RETURN a.uuid AS source_uuid,
           b.uuid AS target_uuid,
           a.name AS source_name_enc,
           b.name AS target_name_enc,
           f.uuid AS uuid,
           f.fact AS fact_enc,
           f.relation_type AS relation_type,
           f.valid_from AS valid_from,
           f.valid_to AS valid_to,
           f.created_at AS created_at
    ORDER BY f.created_at DESC
    LIMIT $limit
    """
    with driver.session(database=database) as session:
        rows = session.run(query, person_id=person_id, limit=limit, now=now).data()

    for row in rows:
        row["fact"] = dec(row.get("fact_enc") or "", person_id)
        row["source_name"] = dec(row.get("source_name_enc") or "", person_id)
        row["target_name"] = dec(row.get("target_name_enc") or "", person_id)
    return rows


def _fetch_recent_facts(
    driver,
    database: str,
    person_id: str,
    limit: int = 100,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch the most recent non-expired, currently valid facts for a person."""
    now = _iso(current_time or datetime.now(timezone.utc))
    query = """
    MATCH (a:Entity {person_id: $person_id})-[f:FACT {person_id: $person_id}]->(b:Entity {person_id: $person_id})
    WHERE f.expired_at IS NULL
      AND (f.valid_from IS NULL OR f.valid_from <= $now)
      AND (f.valid_to IS NULL OR f.valid_to >= $now)
    RETURN a.uuid AS source_uuid,
           b.uuid AS target_uuid,
           a.name AS source_name_enc,
           b.name AS target_name_enc,
           f.uuid AS uuid,
           f.fact AS fact_enc,
           f.relation_type AS relation_type,
           f.valid_from AS valid_from,
           f.valid_to AS valid_to,
           f.created_at AS created_at
    ORDER BY f.created_at DESC
    LIMIT $limit
    """
    with driver.session(database=database) as session:
        rows = session.run(query, person_id=person_id, limit=limit, now=now).data()

    for row in rows:
        row["fact"] = dec(row.get("fact_enc") or "", person_id)
        row["source_name"] = dec(row.get("source_name_enc") or "", person_id)
        row["target_name"] = dec(row.get("target_name_enc") or "", person_id)
    return rows


def retrieve_facts(
    driver,
    database: str,
    person_id: str,
    query_text: str,
    top_k: int = 12,
    bfs_depth: int = 2,
    bfs_top_k: int = 20,
    embed_fn: Optional[Callable] = None,
    current_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Hybrid fact retrieval: vector + BM25 seeds + BFS graph expansion.

    Steps:
    1. Retrieve top-k directly relevant facts via vector similarity + BM25.
    2. Collect seed entity UUIDs from those facts.
    3. Run BFS expansion from the seeds to pull in related facts.
    4. Merge, deduplicate, and rank by retrieval score + recency.

    If query_text is empty, returns the most recent facts instead.
    """
    if not query_text or not query_text.strip():
        return _fetch_recent_facts(driver, database, person_id, limit=top_k, current_time=current_time)

    # 1. Direct vector + BM25 retrieval.
    direct = search_facts(
        driver,
        database,
        person_id,
        query_text,
        top_k=top_k,
        embed_fn=embed_fn,
        current_time=current_time,
    )
    if not direct:
        return []

    # 2. BFS from seed entities found in direct hits.
    seed_uuids: set = set()
    for row in direct:
        seed_uuids.add(row.get("source_uuid"))
        seed_uuids.add(row.get("target_uuid"))

    related = bfs_expand(
        driver,
        database,
        person_id,
        seed_entity_uuids=list(seed_uuids),
        depth=bfs_depth,
        top_k=bfs_top_k,
        current_time=current_time,
    )

    # 3. Merge and deduplicate by fact UUID.
    by_uuid: Dict[str, Dict[str, Any]] = {}
    for row in direct:
        row.setdefault("hop", 0)
        # Slightly prefer directly retrieved facts over graph-expanded ones.
        row["score"] = row.get("score", 0.0) + 0.1
        by_uuid[row["uuid"]] = row

    query_tokens = set(_tokens(query_text))
    for row in related:
        uuid = row["uuid"]
        if uuid in by_uuid:
            continue
        # BFS facts start with a modest base score decayed by hop distance,
        # then get a small overlap boost so relevant related facts rise.
        hop = row.get("hop", 1)
        base = max(0.03, 0.12 / hop)
        fact_tokens = set(_tokens(f"{row.get('source_name', '')} {row.get('target_name', '')} {row.get('fact', '')}"))
        overlap = len(query_tokens & fact_tokens) / max(len(query_tokens), 1)
        row["score"] = base + 0.15 * overlap
        by_uuid[uuid] = row

    # 4. Rank by score, tie-break by recency.
    scored = list(by_uuid.values())
    scored.sort(
        key=lambda r: (
            r.get("score", 0.0),
            r.get("created_at") or "",
        ),
        reverse=True,
    )
    return scored[:top_k]


def format_context(facts: List[Dict[str, Any]]) -> str:
    """Format retrieved facts into a Zep-style context block."""
    if not facts:
        return "No relevant facts."
    lines = []
    for f in facts:
        valid = ""
        if f.get("valid_from") or f.get("valid_to"):
            valid = f" (Date range: {f.get('valid_from') or 'unknown'} to {f.get('valid_to') or 'present'})"
        lines.append(f"- {f['source_name']} {f['relation_type']} {f['target_name']}: {f['fact']}{valid}")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Episode helpers
# -----------------------------------------------------------------------------

def create_episode(
    driver,
    database: str,
    person_id: str,
    body: str,
    source: str = "conversation",
    episode_id: Optional[str] = None,
) -> str:
    """Create a new Episode node and link it to the Person."""
    episode_id = episode_id or f"ep-{uuid.uuid4().hex[:12]}"
    query = """
    MERGE (p:Person {id: $person_id})
    CREATE (ep:Episode {
        id: $episode_id,
        person_id: $person_id,
        body: $body,
        source: $source,
        created_at: $created_at
    })
    MERGE (p)-[:HAS_EPISODE]->(ep)
    RETURN ep.id AS id
    """
    with driver.session(database=database) as session:
        session.run(
            query,
            person_id=person_id,
            episode_id=episode_id,
            body=body,
            source=source,
            created_at=_now_iso(),
        )
    return episode_id
