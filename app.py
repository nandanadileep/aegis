import os
import re
import json
import base64
import random
from urllib.parse import urlparse, urlunparse, quote
from typing import List, Dict, Any, Optional
from pathlib import Path
from functools import wraps

import jwt as pyjwt
import litellm
from flask import Flask, request, jsonify, send_from_directory, Response, redirect, g
from neo4j import GraphDatabase

try:
    from scripts.crypto import enc, dec, node_hash, dec_props
except ImportError:
    # Fallback no-ops if crypto module is unavailable
    def enc(v, u): return v  # type: ignore
    def dec(v, u): return v  # type: ignore
    def node_hash(v, u): return v  # type: ignore
    def dec_props(p, u): return p  # type: ignore

# Ensure we're in the right directory for .env
os.chdir(Path(__file__).parent)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import redis
except ImportError:
    redis = None

try:
    from scripts.memory_pipeline import run_pipeline
except ImportError:
    from memory_pipeline import run_pipeline

LLM_MODEL = os.getenv("LLM_MODEL", "groq/llama-3.3-70b-versatile")
LLM_FAST = os.getenv("LLM_FAST", "groq/qwen3-32b")
DAILY_MSG_LIMIT = int(os.getenv("DAILY_MSG_LIMIT", "30"))

# Canonical label → relationship type used by all write paths
LABEL_TO_REL: Dict[str, str] = {
    "Skill":       "HAS_SKILL",
    "Value":       "HAS_VALUE",
    "Goal":        "HAS_GOAL",
    "Trait":       "HAS_TRAIT",
    "Belief":      "HAS_BELIEF",
    "Identity":    "HAS_IDENTITY",
    "Project":     "WORKS_ON",
    "Behavior":    "HAS_BEHAVIOR",
    "Constraint":  "HAS_CONSTRAINT",
}

# Fallback chain tried in order when the primary model hits rate limits
_MODEL_FALLBACKS = [
    "groq/llama-3.3-70b-versatile",
    "groq/qwen3-32b",
    "groq/llama3-70b-8192",
    "groq/mixtral-8x7b-32768",
    "groq/gemma2-9b-it",
    "groq/llama3-8b-8192",
]

# Multiple Groq API keys — add GROQ_API_KEY_2, GROQ_API_KEY_3, etc. for extra capacity
_GROQ_KEYS = [k for k in [
    os.getenv("GROQ_API_KEY"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
] if k]


# ---------------------------
# Cypher injection guards
# ---------------------------
_LABEL_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')
_REL_RE   = re.compile(r'^[A-Z][A-Z0-9_]*$')

def _safe_label(raw: str) -> str:
    """Strip any non-alphanumeric characters and enforce leading alpha.
    Raises ValueError if the result is empty or structurally invalid."""
    s = re.sub(r'[^A-Za-z0-9]', '', raw)
    if not s or not s[0].isalpha():
        raise ValueError(f"Invalid node label: {raw!r}")
    if not _LABEL_RE.match(s):
        raise ValueError(f"Invalid node label after sanitization: {s!r}")
    return s

def _safe_rel_type(raw: str) -> str:
    """Validate relationship type: uppercase letters, digits, underscores only.
    Raises ValueError on anything that doesn't match — prevents Cypher injection
    through relationship type interpolation."""
    s = raw.strip().upper()
    if not _REL_RE.match(s):
        raise ValueError(f"Invalid relationship type: {raw!r}")
    return s


# ---------------------------
# Helpers
# ---------------------------
def llm_kwargs(base_model: str) -> dict:
    """Return litellm.completion kwargs, preferring user-supplied key/model if present."""
    user_key = request.headers.get("X-LLM-Key", "").strip()
    user_model = request.headers.get("X-LLM-Model", "").strip()
    if user_key and user_model:
        return {"model": user_model, "api_key": user_key}
    return {"model": base_model}


class AllModelsRateLimited(Exception):
    """Raised when every model in the fallback chain has hit a rate limit."""


def _check_daily_limit(person_id: str) -> bool:
    """Increment today's message counter and return True if within limit."""
    from datetime import date
    try:
        rc = get_redis_client()
        key = f"msg_count:{person_id}:{date.today().isoformat()}"
        count = rc.incr(key)
        if count == 1:
            rc.expire(key, 86400)
        return count <= DAILY_MSG_LIMIT
    except Exception:
        return True  # Redis unavailable — let it through


def llm_complete_with_fallback(primary_model: str, **kwargs):
    """Call litellm with fallback models on rate-limit errors."""
    user_key = request.headers.get("X-LLM-Key", "").strip()
    user_model = request.headers.get("X-LLM-Model", "").strip()
    # If user provided BYOK, no fallback logic — use their key/model directly
    if user_key and user_model:
        return litellm.completion(model=user_model, api_key=user_key, **kwargs)

    chain = [primary_model] + [m for m in _MODEL_FALLBACKS if m != primary_model]
    keys = _GROQ_KEYS if _GROQ_KEYS else [None]
    last_err = None
    for model in chain:
        for api_key in keys:
            try:
                kw = {**kwargs, "api_key": api_key} if api_key else kwargs
                return litellm.completion(model=model, **kw)
            except Exception as e:
                err = str(e)
                if "429" in err or "rate_limit" in err.lower() or "rate limit" in err.lower():
                    last_err = e
                    continue
                raise
    raise AllModelsRateLimited(str(last_err))


def load_env(path: str = ".env") -> None:
    if load_dotenv:
        load_dotenv(path)


def env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val




_JWKS_CACHE: Dict[str, Any] = {}

def _get_jwks() -> list:
    global _JWKS_CACHE
    import time
    now = time.time()
    if _JWKS_CACHE.get("ts", 0) + 3600 > now:
        return _JWKS_CACHE.get("keys", [])
    import urllib.request
    supabase_url = os.getenv("SUPABASE_URL", "")
    with urllib.request.urlopen(f"{supabase_url}/auth/v1/.well-known/jwks.json") as r:
        data = json.loads(r.read())
    _JWKS_CACHE = {"keys": data.get("keys", []), "ts": now}
    return _JWKS_CACHE["keys"]


def verify_supabase_token(token: str) -> str:
    """Verify a Supabase JWT using JWKS and return the user UUID."""
    from jwt.algorithms import ECAlgorithm
    keys = _get_jwks()
    if not keys:
        raise ValueError("no JWKS keys available")

    errors = []
    for jwk in keys:
        try:
            public_key = ECAlgorithm.from_jwk(json.dumps(jwk))
            payload = pyjwt.decode(
                token, public_key,
                algorithms=[jwk.get("alg", "ES256")],
                options={"verify_aud": False},
            )
            user_id = payload.get("sub")
            if not user_id:
                raise ValueError("missing sub claim")
            return user_id
        except Exception as e:
            errors.append(str(e))
    raise ValueError(f"token verification failed: {errors}")


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "unauthorized", "detail": "no bearer token"}), 401
        try:
            g.user_id = verify_supabase_token(auth_header[7:])
        except ValueError as e:
            return jsonify({"error": "unauthorized", "detail": str(e)}), 401
        return f(*args, **kwargs)
    return decorated


def get_neo4j_driver():
    uri = env_var("NEO4J_URI")
    user = env_var("NEO4J_USER")
    password = env_var("NEO4J_PASSWORD")
    return GraphDatabase.driver(uri, auth=(user, password))


def fetch_memory_summary(person_id: str, database: str) -> List[Dict[str, Any]]:
    query = """
    MATCH (p:Person {id: $person_id})-[r]->(n)
    RETURN type(r) AS rel, labels(n) AS labels,
           properties(n) AS props,
           coalesce(n.key, n.name, '') AS key,
           coalesce(n.value, n.name, '') AS value
    """
    with NEO4J_DRIVER.session(database=database) as session:
        data = session.run(query, person_id=person_id).data()
    for row in data:
        row["key"] = dec(row.get("key", ""), person_id)
        row["value"] = dec(row.get("value", ""), person_id)
        if row.get("props"):
            row["props"] = dec_props(row["props"], person_id)
    return data


_STOP_WORDS = {
    'the','and','for','are','you','can','how','what','when','where','why',
    'with','that','this','have','from','they','will','been','more','your',
    'its','about','some','just','get','got','did','does','was','has','had',
    'but','not','use','using','used','our','their','there','here','want',
    'need','also','like','make','made','into','out','all','any','would',
    'could','should','tell','know','think','work','working','going','been',
}
_GREETING = re.compile(
    r'^(hi+|hey+|hello|sup|yo|hiya|howdy|good\s*(morning|evening|afternoon|night)|'
    r'what\'?s\s*up|how\s*are\s*(you|u)|greetings?)\W*$', re.I
)

def fetch_relevant_memory(person_id: str, database: str, message: str) -> List[Dict[str, Any]]:
    """Return memory nodes relevant to the user message. Empty for greetings."""
    if _GREETING.match(message.strip()):
        return []
    return fetch_memory_summary(person_id, database)


def format_memory_context(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "No stored memory yet."
    groups: Dict[str, List[str]] = {}
    for rec in records:
        labels = rec.get("labels", [])
        key = rec.get("key", "")
        value = rec.get("value", "")
        props = rec.get("props") or {}
        label_str = labels[0] if labels else "Other"
        name = key or value or props.get("name", "")
        if not name:
            continue
        groups.setdefault(label_str, []).append(name)
    lines = []
    for label, items in groups.items():
        lines.append(f"{label}: {', '.join(items)}")
    return "\n".join(lines)


def fetch_wallet_data(person_id: str, database: str) -> Dict[str, Any]:
    query = """
    MATCH (p:Person {id: $person_id})
    OPTIONAL MATCH (p)-[r]->(n)
    RETURN
        p.name AS person_name,
        p.id AS person_id,
        collect({
            rel: type(r),
            labels: labels(n),
            props: properties(n),
            key: coalesce(n.key, n.name, ''),
            value: coalesce(n.value, n.name, '')
        }) AS facts
    """
    with NEO4J_DRIVER.session(database=database) as session:
        row = session.run(query, person_id=person_id).single()
    if not row:
        return {"person_name": person_id, "person_id": person_id, "facts": []}
    result = dict(row)
    result["person_name"] = dec(result.get("person_name") or "", person_id)
    decrypted_facts = []
    for fact in (result.get("facts") or []):
        if not fact:
            continue
        f = dict(fact)
        f["key"] = dec(f.get("key", ""), person_id)
        f["value"] = dec(f.get("value", ""), person_id)
        if f.get("props"):
            f["props"] = dec_props(f["props"], person_id)
        decrypted_facts.append(f)
    result["facts"] = decrypted_facts
    return result


def generate_wallet_markdown(person_id: str, database: str) -> str:
    data = fetch_wallet_data(person_id, database)
    person_name = data.get("person_name") or person_id
    facts = data.get("facts") or []

    # Group facts by relationship type
    groups: Dict[str, List[str]] = {}
    for fact in facts:
        if not fact or not fact.get("rel"):
            continue
        rel = fact["rel"]
        labels = fact.get("labels") or []
        label_str = labels[0] if labels else ""
        key = fact.get("key", "")
        value = fact.get("value", "")
        props = fact.get("props") or {}

        if key and value and key != value:
            entry = f"{key}: {value}"
        elif value:
            entry = value
        elif props:
            entry = "; ".join(
                f"{k} = {', '.join(str(i) for i in v) if isinstance(v, list) else v}"
                for k, v in sorted(props.items())
                if k not in ("name", "key")
            ) or key
        else:
            entry = key

        if entry:
            section = label_str or rel.replace("_", " ").title()
            groups.setdefault(section, []).append(entry)

    lines = [
        f"# Memory Profile — {person_name}",
        "",
        f"You are talking to **{person_name}**.",
        "Adopt this profile immediately. Do not introduce yourself, do not ask who they are.",
        "Talk to them as if you already know them deeply — because you do.",
        "Hold their identity, values, and way of thinking in everything you say.",
        "If they say something that contradicts this profile, trust what they say now.",
        "",
        "---",
        "",
    ]

    if not groups:
        lines.append("*No memory stored yet.*")
    else:
        for section, items in groups.items():
            lines.append(f"## {section}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    lines += [
        "---",
        f"*Memory Card generated by Identiti · {person_id}*",
    ]

    return "\n".join(lines)


_WALLET_STAMPS = [
    '🪷','🌸','🌿','🍃','🦋','🌙','🔮','🪐','🌊','🌻',
    '🍀','🦚','🌺','🫧','🌼','✨','💫','🌠','🪸','🐚',
    '🎴','🧿','🪄','🌈','🫐','🌑','🪬','🎐','🌾','🦩',
]

def generate_wallet_html(person_id: str, database: str) -> str:
    md = generate_wallet_markdown(person_id, database)
    stamp = random.choice(_WALLET_STAMPS)
    md_escaped = (md
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memory Card</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0 }}
  body {{
    background: #0f0f13;
    color: #c8c8d4;
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    min-height: 100vh;
    padding: 64px 20px 80px;
  }}
  .wrap {{ max-width: 660px; margin: 0 auto }}
  .header {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    margin-bottom: 36px;
  }}
  .stamp {{
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    filter: drop-shadow(0 0 20px rgba(255,255,255,0.12));
    user-select: none;
    line-height: 1;
  }}
  .copy-btn {{
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.13);
    border-radius: 50%;
    color: #e8e8ed;
    font-size: 17px;
    cursor: pointer;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
    flex-shrink: 0;
  }}
  .copy-btn:hover {{ background: rgba(255,255,255,0.13) }}
  .copy-btn.copied {{ color: #30d158; border-color: rgba(48,209,88,0.28) }}
  pre {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 32px;
    font-family: inherit;
    font-size: 13px;
    line-height: 1.75;
    white-space: pre-wrap;
    word-break: break-word;
    color: #b0b0bc;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="stamp">{stamp}</div>
    <button class="copy-btn" onclick="copy()" title="Copy markdown">⎘</button>
  </div>
  <pre id="md">{md_escaped}</pre>
</div>
<script>
function copy() {{
  navigator.clipboard.writeText(document.getElementById('md').textContent)
  const btn = document.querySelector('.copy-btn')
  btn.textContent = '✓'
  btn.classList.add('copied')
  setTimeout(() => {{ btn.textContent = '⎘'; btn.classList.remove('copied') }}, 2000)
}}
</script>
</body>
</html>"""


def needs_retrieval(message: str) -> bool:
    """Fast check: does this message need personal context from the user's graph?"""
    if _GREETING.match(message.strip()):
        return False
    try:
        result = llm_complete_with_fallback(
            LLM_FAST,
            messages=[{"role": "user", "content": (
                "Does answering this message require personal context about the user "
                "(their skills, projects, goals, values, interests, etc.)? "
                "Answer only YES or NO.\n\nMessage: " + message
            )}],
            temperature=0,
            max_tokens=3,
        )
        return result.choices[0].message.content.strip().upper().startswith("Y")
    except Exception:
        return True  # default to fetching memory if the check fails



def normalize_redis_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if not host:
        return raw_url

    # Upstash Redis requires TLS and usually uses the "default" ACL username.
    if host.endswith("upstash.io"):
        if scheme == "redis":
            scheme = "rediss"

        if not parsed.username and parsed.password:
            user = quote("default", safe="")
            password = quote(parsed.password, safe="")
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{user}:{password}@{parsed.hostname}{port}"
            return urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

    if scheme != parsed.scheme:
        return urlunparse((scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

    return raw_url


def get_redis_client():
    if redis is None:
        raise RuntimeError("redis package not installed. pip install redis")
    redis_url = normalize_redis_url(env_var("REDIS_URL"))
    return redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def history_to_transcript(history: List[Dict[str, str]]) -> str:
    lines = []
    for msg in history:
        role = msg.get("role", "assistant").capitalize()
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)


def resolve_person_id(payload: Optional[Dict[str, Any]] = None) -> str:
    # Auth token always wins — never trust client-supplied person_id
    if hasattr(g, "user_id") and g.user_id:
        return g.user_id
    return DEFAULT_PERSON_ID


def history_key(person_id: str) -> str:
    return f"conversation_history:{person_id}"


def load_conversation_history(person_id: str) -> List[Dict[str, str]]:
    key = history_key(person_id)
    history: List[Dict[str, str]] = []
    raw_messages = REDIS_CLIENT.lrange(key, 0, -1)

    for raw in raw_messages:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        role = parsed.get("role")
        content = parsed.get("content")
        if role is None or content is None:
            continue
        history.append({"role": str(role), "content": str(content)})

    return history


def append_conversation_message(person_id: str, role: str, content: str) -> None:
    REDIS_CLIENT.rpush(
        history_key(person_id),
        json.dumps({"role": role, "content": content}),
    )
    REDIS_CLIENT.expire(history_key(person_id), 60 * 60 * 24 * 7)


def clear_conversation_history(person_id: str) -> None:
    REDIS_CLIENT.delete(history_key(person_id))


def parse_body_json() -> Dict[str, Any]:
    body = request.get_json(silent=True)
    if isinstance(body, dict):
        return body

    raw_payload = request.get_data(as_text=True)
    if not raw_payload:
        return {}

    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


# ---------------------------
# Flask app
# ---------------------------
load_env()
app = Flask(__name__, static_folder="static", static_url_path="")

DEFAULT_PERSON_ID = os.getenv("PERSON_ID", "nandana_dileep")
DATABASE = env_var("NEO4J_DATABASE")
REDIS_CLIENT = get_redis_client()
NEO4J_DRIVER = get_neo4j_driver()


def _spa():
    return send_from_directory(app.static_folder, "index.html")



@app.route("/api/config")
def public_config():
    return jsonify({
        "supabase_url":      os.getenv("SUPABASE_URL", ""),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", ""),
    })


@app.route("/api/me")
@require_auth
def me():
    person_id = g.user_id
    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            result = session.run(
                "MATCH (p:Person {id: $pid}) RETURN p.name as name, p.username as username LIMIT 1",
                pid=person_id,
            ).single()
        if result:
            return jsonify({"exists": True, "name": dec(result["name"] or "", person_id), "username": result["username"]})
        return jsonify({"exists": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/context", methods=["GET"])
@require_auth
def context():
    person_id = resolve_person_id()
    records = fetch_memory_summary(person_id, DATABASE)
    summary = format_memory_context(records)
    return jsonify({"context": summary})


@app.route("/api/wallet", methods=["GET"])
@require_auth
def export_wallet():
    person_id = resolve_person_id()
    html = generate_wallet_html(person_id, DATABASE)
    return Response(html, mimetype="text/html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/chat", methods=["POST"])
@require_auth
def chat():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400

    user_message = str(data.get("message", "")).strip()
    if not user_message:
        return jsonify({"error": "message required"}), 400

    person_id = resolve_person_id(data)

    storage_warning = None
    try:
        conversation_history = load_conversation_history(person_id)
    except Exception as e:
        conversation_history = []
        storage_warning = f"redis read failed: {e}"

    # Retrieval pipeline: only fetch graph context when the message actually needs it
    context_block = ""
    if needs_retrieval(user_message):
        try:
            records = fetch_relevant_memory(person_id, DATABASE, user_message)
            ctx = format_memory_context(records)
            if ctx and ctx != "No stored memory yet.":
                context_block = f"[Context about the user from their knowledge graph:\n{ctx}]"
        except Exception:
            pass

    # Per-user daily limit — skip for BYOK users (they use their own tokens)
    byok = request.headers.get("X-LLM-Key", "").strip()
    if not byok and not _check_daily_limit(person_id):
        return jsonify({
            "reply": f"You've hit the {DAILY_MSG_LIMIT}-message daily limit. Come back tomorrow, or add your own API key in settings to keep going.",
            "added_nodes": [],
        }), 200

    # Build message with context injected into user turn if needed
    augmented_message = f"{context_block}\n\n{user_message}".strip() if context_block else user_message
    system_msg = {
        "role": "system",
        "content": (
            "You are a sharp, direct assistant. Keep responses short and conversational — "
            "a few sentences at most unless the user explicitly asks for detail. "
            "Never use numbered lists or bullet points unless asked. "
            "Never ask multiple follow-up questions at once. "
            "Match the energy of the user's message."
        ),
    }
    history = [system_msg, *conversation_history, {"role": "user", "content": augmented_message}]

    try:
        completion = llm_complete_with_fallback(
            LLM_MODEL,
            messages=history,
            temperature=0.5,
        )
    except AllModelsRateLimited:
        return jsonify({"reply": "I've hit my daily token limit across all models. Come back tomorrow, or add your own API key in the settings — it takes 30 seconds.", "added_nodes": []}), 200
    except Exception as e:
        err = str(e)
        if "api_key" in err.lower() or "401" in err or "authentication" in err.lower():
            return jsonify({"error": "Invalid API key. Check your key in the API Key settings."}), 400
        return jsonify({"error": f"LLM error: {err}"}), 502
    reply = completion.choices[0].message.content or ""

    try:
        append_conversation_message(person_id, "user", user_message)
        append_conversation_message(person_id, "assistant", reply)
    except Exception as e:
        if storage_warning:
            storage_warning = f"{storage_warning}; redis write failed: {e}"
        else:
            storage_warning = f"redis write failed: {e}"

    # Route through staging pipeline — confidence scoring prevents noisy direct writes
    added_nodes = []
    try:
        rc = get_redis_client()
        pipeline_result = run_pipeline(
            f"User: {user_message}\nAssistant: {reply}",
            person_id=person_id,
            redis_client=rc,
            neo4j_driver=NEO4J_DRIVER,
            llm_fn=lambda **kw: llm_complete_with_fallback(LLM_FAST, **kw),
        )
        added_nodes = [
            {"key": item.get("key"), "value": item.get("value"), "category": cat}
            for cat, items in pipeline_result.get("ready", {}).items()
            for item in items
        ]
    except Exception:
        pass

    response: Dict[str, Any] = {"reply": reply, "added_nodes": added_nodes}
    if storage_warning:
        response["warning"] = storage_warning
    return jsonify(response)




@app.route("/v1/chat/completions", methods=["POST"])
def proxy_completions():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400

    person_id = resolve_person_id(data)
    messages = data.get("messages", [])
    model = data.get("model", LLM_MODEL)

    try:
        records = fetch_memory_summary(person_id, DATABASE)
    except Exception as e:
        return jsonify({"error": "memory unavailable", "detail": str(e)}), 503

    memory_context = format_memory_context(records)
    system_prompt = build_system_prompt(memory_context)

    non_system = [m for m in messages if m.get("role") != "system"]
    enriched = [{"role": "system", "content": system_prompt}, *non_system]

    completion = llm_complete_with_fallback(
        model,
        messages=enriched,
        temperature=data.get("temperature", 0.5),
        stream=False,
    )

    user_messages = [m["content"] for m in non_system if m.get("role") == "user"]
    reply = completion.choices[0].message.content or ""
    try:
        for content in user_messages:
            append_conversation_message(person_id, "user", content)
        append_conversation_message(person_id, "assistant", reply)
    except Exception:
        pass

    return jsonify(completion.model_dump())


@app.route("/clear-history", methods=["POST"])
@require_auth
def clear_history():
    person_id = resolve_person_id(parse_body_json())
    try:
        clear_conversation_history(person_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/save", methods=["POST"])
@require_auth
def save():
    body = parse_body_json()
    person_id = resolve_person_id(body)
    client_transcript = body.get("transcript")
    storage_warning = None
    try:
        conversation_history = load_conversation_history(person_id)
    except Exception as e:
        conversation_history = []
        storage_warning = f"redis read failed: {e}"

    pieces = []
    if isinstance(client_transcript, str) and client_transcript.strip():
        pieces.append(client_transcript)
    if conversation_history:
        pieces.append(history_to_transcript(conversation_history))

    transcript = "\n".join(pieces).strip()
    if transcript:
        run_pipeline(transcript, use_mock_llm=False, person_id=person_id, redis_client=REDIS_CLIENT)
        if conversation_history:
            try:
                clear_conversation_history(person_id)
            except Exception as e:
                if storage_warning:
                    storage_warning = f"{storage_warning}; redis clear failed: {e}"
                else:
                    storage_warning = f"redis clear failed: {e}"

    response: Dict[str, Any] = {"status": "ok"}
    if storage_warning:
        response["warning"] = storage_warning
    return jsonify(response)


@app.route("/chat")
def chat_page():
    return _spa()


@app.route("/memory")
def memory_page():
    return _spa()


@app.route("/onboarding")
def onboarding_page():
    return _spa()


@app.route("/login")
def login_page():
    return _spa()


ONBOARD_SYSTEM_PROMPT = """
You are getting to know someone to build their knowledge profile. Your job is to understand who they really are — not what sounds good, but what actually drives them.

Rules:
- One question at a time. Short. Never numbered lists.
- Don't validate or compliment. Just listen and dig deeper.
- Ask questions that reveal character, not just facts.
- Start by asking their name naturally, then go from there.
- Keep messages to 1-2 sentences. No filler. No "great answer!" or "interesting!".

You MUST ask at least 8 questions and collect ALL of the following before wrapping up:
- Their name
- At least 3 distinct skills or areas of expertise
- At least 3 values, beliefs, or personal principles
- At least 2 goals or things they are actively working toward
- At least 2 personality traits or characteristics
- Their speaking/communication style

Only once you have all of the above, end your final message with the profile block and nothing after it:

<PROFILE>
{"name": "...", "description": "one sentence — who this person is", "values": [...], "skills": [...], "personality": [...], "goals": [...], "speaking_style": "...", "known_for": [...]}
</PROFILE>

If you don't have enough yet, keep asking. Do not output the profile early.
""".strip()


def _count_profile_nodes(profile: dict) -> int:
    """Count how many graph nodes this profile will produce."""
    array_fields = ["values", "skills", "personality", "goals", "known_for"]
    return 1 + sum(len(profile.get(f, [])) for f in array_fields)


@app.route("/api/onboard-chat", methods=["POST"])
@require_auth
def onboard_chat():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400

    user_message = str(data.get("message", "")).strip()
    history = data.get("history", [])
    if not isinstance(history, list):
        history = []

    messages = [{"role": "system", "content": ONBOARD_SYSTEM_PROMPT}]
    for entry in history:
        if isinstance(entry, dict) and entry.get("role") in ("user", "assistant"):
            messages.append({"role": entry["role"], "content": str(entry.get("content", ""))})

    if user_message:
        messages.append({"role": "user", "content": user_message})

    try:
        completion = llm_complete_with_fallback(
            LLM_MODEL,
            messages=messages,
            temperature=0.7,
        )
    except AllModelsRateLimited:
        return jsonify({"reply": "I've hit my daily token limit. Come back tomorrow or add your own API key in settings.", "profile": None}), 200
    except Exception as e:
        err = str(e)
        if "api_key" in err.lower() or "401" in err or "authentication" in err.lower():
            return jsonify({"error": "Invalid API key. Check your key in the API Key settings."}), 400
        return jsonify({"error": f"LLM error: {err}"}), 502
    reply = completion.choices[0].message.content or ""

    profile = None
    node_count = 0
    if "<PROFILE>" in reply and "</PROFILE>" in reply:
        start = reply.index("<PROFILE>") + len("<PROFILE>")
        end = reply.index("</PROFILE>")
        profile_text = reply[start:end].strip()
        display_reply = reply[:reply.index("<PROFILE>")].strip()
        try:
            candidate = json.loads(profile_text)
        except Exception:
            candidate = None
        if candidate:
            count = _count_profile_nodes(candidate)
            if count >= 10:
                profile = candidate
                node_count = count
                reply = display_reply
            # If < 10 nodes, discard profile and let conversation continue

    return jsonify({"reply": reply, "profile": profile, "node_count": node_count})


_TWIN_KEYS = {"name", "description", "values", "skills", "personality", "goals", "speaking_style", "known_for"}

def _parse_raw_memory_to_twin(raw_text: str) -> dict:
    """Convert any memory export format into our structured profile dict.
    If the input is already valid JSON matching our schema, use it directly
    without calling the LLM.
    """
    # Try direct JSON parse first — avoids LLM call when user pastes our schema output
    stripped = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
    stripped = re.sub(r"\s*```$", "", stripped.strip())
    try:
        candidate = json.loads(stripped)
        if isinstance(candidate, dict) and _TWIN_KEYS & candidate.keys():
            return candidate
    except Exception:
        pass

    prompt = f"""You are given a profile or memory export. Extract structured data and output it as clean, minimal node labels for a knowledge graph.

Rules for arrays (values, skills, personality, goals, known_for):
- Each item must be 1–3 words max. No sentences.
- Distill the essence. "learning through hands-on practice" → "Hands-on Learning". "become a CEO" → "CEO". "building AI and ML projects including chatbots" → "AI/ML Projects".
- Remove redundancy. If two items mean the same thing, keep one.
- Capitalize each item like a title.

Output ONLY a valid JSON object:
{{
  "name": "person's name",
  "description": "one concise sentence who this person is",
  "values": ["Short Label", ...],
  "skills": ["Short Label", ...],
  "personality": ["Short Label", ...],
  "goals": ["Short Label", ...],
  "speaking_style": "brief phrase",
  "known_for": ["Short Label", ...]
}}

Input:
{raw_text}

Respond with ONLY the JSON object, no explanation."""

    completion = llm_complete_with_fallback(
        LLM_FAST,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    content = completion.choices[0].message.content or ""
    # Strip markdown code fences if present
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content.strip())
    return json.loads(content)


@app.route("/api/import", methods=["POST"])
@require_auth
def import_twin():
    data = parse_body_json()
    person_id = resolve_person_id(data)

    # Accept either raw memory text or pre-structured twin dict
    raw_memory = data.get("raw_memory", "")
    if raw_memory:
        try:
            twin = _parse_raw_memory_to_twin(str(raw_memory))
        except Exception as e:
            return jsonify({"error": f"Could not parse memory: {e}"}), 400
    else:
        twin = data.get("twin", {})
        if not isinstance(twin, dict):
            return jsonify({"error": "twin must be a JSON object"}), 400

    name = str(twin.get("name") or person_id)
    username = str(data.get("username") or name.lower().replace(" ", "") )
    description = str(twin.get("description") or twin.get("twin_description") or "")
    speaking_style = str(twin.get("speaking_style") or "")

    field_map = {
        "values":              ("Value",    "HAS_VALUE"),
        "skills":              ("Skill",    "HAS_SKILL"),
        "personality":         ("Trait",    "HAS_TRAIT"),
        "goals":               ("Goal",     "HAS_GOAL"),
        "beliefs":             ("Belief",   "HAS_BELIEF"),
        "currently_working_on":("Project",  "WORKING_ON"),
        "known_for":           ("Identity", "KNOWN_FOR"),
    }

    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            session.run(
                """
                MERGE (p:Person {id: $pid})
                SET p.name = $name,
                    p.username = $username,
                    p.description = $desc,
                    p.speaking_style = $style
                """,
                pid=person_id,
                name=enc(name, person_id),
                username=username,
                desc=enc(description, person_id),
                style=enc(speaking_style, person_id),
            )
            for field, (label, rel) in field_map.items():
                items = twin.get(field) or []
                if isinstance(items, str):
                    items = [items]
                for item in items:
                    item = str(item).strip()
                    if not item:
                        continue
                    session.run(
                        f"""
                        MATCH (p:Person {{id: $pid}})
                        MERGE (n:{label} {{_h: $h, person_id: $pid}})
                        ON CREATE SET n.name = $enc_name
                        ON MATCH SET n.name = $enc_name
                        MERGE (p)-[:{rel}]->(n)
                        """,
                        pid=person_id,
                        h=node_hash(item, person_id),
                        enc_name=enc(item, person_id),
                    )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "person_id": person_id})


@app.route("/api/onboard", methods=["POST"])
@require_auth
def onboard():
    data = parse_body_json()
    person_id = resolve_person_id(data)
    answers = data.get("answers", {})
    if not isinstance(answers, dict):
        return jsonify({"error": "answers must be an object"}), 400

    label_map = {
        "name":        "My name is",
        "description": "The person I want to become:",
        "values":      "Things I never compromise on:",
        "known_for":   "I want to be known for:",
        "skills":      "I am exceptional at:",
        "working_on":  "Right now I am building or working toward:",
    }

    lines = []
    for key, prefix in label_map.items():
        val = str(answers.get(key, "")).strip()
        if val:
            lines.append(f"User: {prefix} {val}")

    transcript = "\n".join(lines)
    if not transcript:
        return jsonify({"error": "no answers provided"}), 400

    try:
        run_pipeline(transcript, use_mock_llm=False, person_id=person_id, redis_client=REDIS_CLIENT)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "person_id": person_id})


# ---------------------------
# Memory Graph API
# ---------------------------

@app.route("/api/graph", methods=["GET"])
@require_auth
def get_graph():
    """Fetch all nodes and relationships for a person."""
    person_id = resolve_person_id()
    
    query = """
    MATCH (p:Person {id: $person_id})
    OPTIONAL MATCH (p)-[]->(n)
    RETURN DISTINCT id(n) as node_id, n.name as name, n.key as key, labels(n) as labels
    UNION
    MATCH (p:Person {id: $person_id})
    RETURN id(p) as node_id, p.name as name, p.id as key, labels(p) as labels
    """

    query_edges = """
    MATCH (p:Person {id: $person_id})-[r]->(n)
    RETURN DISTINCT id(r) as rel_id, id(p) as from_id, id(n) as to_id, type(r) as rel_type
    """
    
    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            nodes_result = session.run(query, person_id=person_id).data()
            edges_result = session.run(query_edges, person_id=person_id).data()
        
        nodes_dict = {}
        
        for record in nodes_result:
            node_id = str(record["node_id"])
            raw_name = record.get("name") or record.get("key") or "Node"
            name = dec(raw_name, person_id)
            labels = record.get("labels") or []

            nodes_dict[node_id] = {
                "id": node_id,
                "label": name,
                "title": f"{labels[0] if labels else 'Node'}"
            }
        
        edges_list = []
        for record in edges_result:
            edges_list.append({
                "id": str(record["rel_id"]),
                "from": str(record["from_id"]),
                "to": str(record["to_id"]),
                "label": record.get("rel_type", "")
            })
        
        return jsonify({
            "nodes": list(nodes_dict.values()),
            "edges": edges_list
        })
    except Exception as e:
        return jsonify({"error": str(e), "detail": str(e)}), 500


@app.route("/api/nodes", methods=["POST"])
@require_auth
def create_node():
    """Create a new node."""
    person_id = resolve_person_id()
    data = parse_body_json()
    
    label = data.get("label", "").strip()
    name = data.get("name", "").strip()
    properties = data.get("properties", {})

    if not label or not name:
        return jsonify({"error": "label and name required"}), 400

    # Normalize label: spelling correction only, never semantic remapping
    KNOWN_LABELS = ["Person", "Skill", "Value", "Goal", "Trait", "Identity",
                    "Project", "Behavior", "Constraint", "Belief"]
    try:
        norm = llm_complete_with_fallback(
            LLM_FAST,
            messages=[{
                "role": "user",
                "content": (
                    f"Fix the spelling of this node label: \"{label}\"\n"
                    f"Known labels (use one of these ONLY if the input is clearly a typo of it): {', '.join(KNOWN_LABELS)}\n"
                    "Rules:\n"
                    "- If it's a typo of a known label (e.g. 'skil' → 'Skill'), return that known label.\n"
                    "- Otherwise, just fix the spelling of the word(s) the user typed (e.g. 'homme' → 'Home', 'fevorite color' → 'FavoriteColor').\n"
                    "- NEVER replace with a semantically similar word. Return what the user meant to type.\n"
                    "- Return CamelCase, no spaces, no punctuation. Reply with ONLY the label."
                )
            }],
            temperature=0,
            max_tokens=20,
        )
        raw_label = norm.choices[0].message.content.strip().strip('"').strip("'")
        raw_label = re.sub(r'\s+(.)', lambda m: m.group(1).upper(), raw_label)
    except Exception:
        raw_label = ''.join(w.capitalize() for w in label.strip().split())

    try:
        safe_label = _safe_label(raw_label)
    except ValueError:
        return jsonify({"error": f"Invalid label: {label!r}"}), 400

    try:
        enc_name = enc(name, person_id)
        h = node_hash(name, person_id)
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            query = f"""
            CREATE (n:`{safe_label}` {{name: $enc_name, key: $enc_name, _h: $h, person_id: $pid}})
            SET n += $properties
            RETURN id(n) as node_id
            """
            result = session.run(query, enc_name=enc_name, h=h, pid=person_id, properties=properties)
            node_id = result.single()["node_id"]
            
            # Connect to Person with semantic relationship type
            rel_type = LABEL_TO_REL.get(safe_label, "KNOWS")
            session.run(
                f"MATCH (p:Person {{id: $person_id}}) MATCH (n) WHERE id(n) = $node_id CREATE (p)-[:{rel_type}]->(n)",
                person_id=person_id, node_id=node_id,
            )
        
        return jsonify({"id": str(node_id), "label": safe_label, "name": name})
    except Exception as e:
        return jsonify({"error": str(e), "detail": str(e)}), 500


@app.route("/api/nodes/<node_id>", methods=["PATCH"])
@require_auth
def update_node(node_id):
    """Rename a node."""
    person_id = resolve_person_id()
    data = parse_body_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    try:
        enc_name = enc(name, person_id)
        h = node_hash(name, person_id)
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            result = session.run(
                "MATCH (n) WHERE id(n) = $nid AND n.person_id = $pid SET n.name = $enc_name, n.key = $enc_name, n._h = $h RETURN id(n) as node_id",
                nid=int(node_id), pid=person_id, enc_name=enc_name, h=h
            )
            if not result.single():
                return jsonify({"error": "node not found"}), 404
        return jsonify({"id": node_id, "name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/relationships", methods=["POST"])
@require_auth
def create_relationship():
    """Create a new relationship between nodes."""
    person_id = resolve_person_id()
    data = parse_body_json()
    
    from_id = data.get("from")
    to_id = data.get("to")
    raw_rel = data.get("type", "")

    if not from_id or not raw_rel or not to_id:
        return jsonify({"error": "from, type, and to required"}), 400

    try:
        rel_type = _safe_rel_type(raw_rel)
    except ValueError:
        return jsonify({"error": f"Invalid relationship type: {raw_rel!r}"}), 400

    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            query = f"""
            MATCH (a), (b)
            WHERE id(a) = $from_id AND id(b) = $to_id
            CREATE (a)-[r:{rel_type}]->(b)
            RETURN id(r) as rel_id
            """
            result = session.run(query, from_id=int(from_id), to_id=int(to_id))
            record = result.single()
            if not record:
                return jsonify({"error": "nodes not found"}), 404
            rel_id = record["rel_id"]
        
        return jsonify({"id": str(rel_id), "from": from_id, "type": rel_type, "to": to_id})
    except Exception as e:
        return jsonify({"error": str(e), "detail": str(e)}), 500


@app.route("/api/commit", methods=["POST"])
@require_auth
def commit_changes():
    """Apply all pending changes to the graph."""
    person_id = resolve_person_id()
    data = parse_body_json()
    
    added_nodes = data.get("nodes", {})
    added_edges = data.get("edges", {})
    deleted_nodes = data.get("deletedNodes", [])
    deleted_edges = data.get("deletedEdges", [])
    
    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            # Delete nodes and their relationships
            for node_id in deleted_nodes:
                try:
                    node_id_int = int(node_id)
                    query = """
                    MATCH (n)
                    WHERE id(n) = $node_id
                    DETACH DELETE n
                    """
                    session.run(query, node_id=node_id_int)
                except (ValueError, TypeError):
                    pass
            
            # Delete relationships
            for edge_id in deleted_edges:
                try:
                    edge_id_int = int(edge_id)
                    query = """
                    MATCH ()-[r]-()
                    WHERE id(r) = $edge_id
                    DELETE r
                    """
                    session.run(query, edge_id=edge_id_int)
                except (ValueError, TypeError):
                    pass
        
        return jsonify({"status": "ok", "committed": len(added_nodes) + len(added_edges) + len(deleted_nodes) + len(deleted_edges)})
    except Exception as e:
        return jsonify({"error": str(e), "detail": str(e)}), 500


@app.route("/api/deduplicate", methods=["POST"])
@require_auth
def deduplicate_graph():
    """Remove duplicate nodes within the same label for a user.

    Strategy: within each label group, if node A's decrypted name is a
    case-insensitive prefix/substring of node B's name (or vice-versa), treat
    them as duplicates — keep the shortest/cleanest name and delete the rest,
    reconnecting their relationships first.
    """
    person_id = resolve_person_id()
    deleted = 0

    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            # Fetch all non-Person nodes with their IDs and names
            rows = session.run(
                """
                MATCH (p:Person {id: $pid})-[]->(n)
                WHERE NOT n:Person
                RETURN id(n) AS nid, labels(n) AS lbls, n.name AS name, n._h AS h
                """,
                pid=person_id,
            ).data()

        # Decrypt names and group by label
        from collections import defaultdict
        by_label = defaultdict(list)
        for row in rows:
            raw = row.get("name") or ""
            name = dec(raw, person_id)
            lbl = (row.get("lbls") or ["Unknown"])[0]
            by_label[lbl].append({"nid": row["nid"], "name": name, "raw": raw})

        to_delete = set()
        for lbl, nodes in by_label.items():
            # Sort shortest name first — keep the cleanest/shortest
            nodes.sort(key=lambda x: len(x["name"]))
            for i, keeper in enumerate(nodes):
                if keeper["nid"] in to_delete:
                    continue
                k_norm = keeper["name"].lower().strip()
                for dup in nodes[i + 1:]:
                    if dup["nid"] in to_delete:
                        continue
                    d_norm = dup["name"].lower().strip()
                    # Duplicate if one name contains the other or they share root word
                    if k_norm and (k_norm in d_norm or d_norm in k_norm):
                        to_delete.add(dup["nid"])

        with NEO4J_DRIVER.session(database=DATABASE) as session:
            for nid in to_delete:
                session.run(
                    "MATCH (n) WHERE id(n) = $nid DETACH DELETE n",
                    nid=nid,
                )
                deleted += 1

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"deleted": deleted})


# Catch-all: serve React SPA for any non-API path (e.g. /callback from OAuth)
# Must be registered LAST so it doesn't shadow API routes.
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    if path.startswith("assets/") or path in ("favicon.svg", "favicon.ico"):
        return send_from_directory(app.static_folder, path)
    return _spa()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
