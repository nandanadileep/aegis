"""
Memory extraction pipeline for AuraDB.

Steps:
1) LLM extraction (Anthropic) -> structured categories.
2) Staging layer with belief scores (staging.json).
3) Threshold check per category.
4) Write to Neo4j when confidence crosses threshold.

Run the module directly to execute a demo with a mock LLM extraction.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple

from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:  # optional
    load_dotenv = None

try:
    from groq import Groq
except ImportError:  # Groq SDK may not be installed in all environments
    Groq = None


# ---------- Configuration ----------
STAGING_PATH = Path("staging.json")
THRESHOLDS = {
    "identity": 0.6,
    "behavior": 0.75,
    "projects": 0.65,
    "constraints": 0.7,
    "values": 0.85,
}


# ---------- Env helpers ----------
def load_env(path: str = ".env") -> None:
    if load_dotenv:
        load_dotenv(path)


def env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


# ---------- LLM extraction ----------
def call_llm_extract(conversation: str, use_mock: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """Return extraction dict keyed by category; each item has key/value/status."""
    if use_mock or not Groq:
        return {
            "identity": [
                {"key": "name", "value": "Nandana Dileep", "status": "confirmation"},
                {"key": "location", "value": "Bangalore", "status": "confirmation"},
            ],
            "behavior": [
                {"key": "tone", "value": "direct and structured", "status": "confirmation"},
            ],
            "projects": [
                {"key": "project", "value": "building AI memory app", "status": "first_mention"},
            ],
            "constraints": [
                {"key": "time", "value": "limited evenings", "status": "first_mention"},
            ],
            "values": [
                {"key": "value", "value": "independence", "status": "explicit_preference"},
            ],
        }

    client = Groq(api_key=env_var("GROQ_API_KEY"))
    prompt = (
        "Extract any new information from the conversation in the five categories. "
        "Return JSON with keys identity, behavior, projects, constraints, values. "
        "Each value is a list of objects with keys: key, value, status "
        "(one of first_mention, confirmation, contradiction, explicit_preference). "
        "Use empty list if nothing new."
    )
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "user", "content": prompt + "\n\nConversation:\n" + conversation}
        ],
    )
    content = completion.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {k: [] for k in THRESHOLDS.keys()}


# ---------- Staging management ----------
def load_staging(path: Path = STAGING_PATH) -> Dict[str, List[Dict[str, Any]]]:
    if not path.exists():
        return {k: [] for k in THRESHOLDS.keys()}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_staging(staging: Dict[str, List[Dict[str, Any]]], path: Path = STAGING_PATH) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2)


def score_update(current: float, status: str) -> float:
    if status == "explicit_preference":
        return 0.9
    if current == 0:
        return 0.4
    if status == "confirmation":
        return current + 0.2 * (1 - current)
    if status == "contradiction":
        return max(0.0, current - 0.3)
    if status == "first_mention":
        return max(current, 0.4)
    return current


def update_staging(staging: Dict[str, List[Dict[str, Any]]], extractions: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    for category, items in extractions.items():
        if category not in staging:
            staging[category] = []
        for item in items or []:
            key = item.get("key")
            value = item.get("value")
            status = item.get("status", "first_mention")
            existing = next((x for x in staging[category] if x.get("key") == key and x.get("value") == value), None)
            if not existing:
                staging[category].append({
                    "key": key,
                    "value": value,
                    "score": score_update(0, status),
                    "history": [status],
                })
            else:
                existing["score"] = score_update(existing.get("score", 0), status)
                history = existing.get("history", [])
                history.append(status)
                existing["history"] = history
    return staging


# ---------- Threshold check ----------
def split_ready(staging: Dict[str, List[Dict[str, Any]]]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
    ready = {k: [] for k in THRESHOLDS}
    remaining = {k: [] for k in THRESHOLDS}
    for category, items in staging.items():
        threshold = THRESHOLDS.get(category, 1.0)
        for item in items:
            if item.get("score", 0) >= threshold:
                ready[category].append(item)
            else:
                remaining[category].append(item)
    return ready, remaining


# ---------- Neo4j write ----------
def write_ready(driver, database: str, person_id: str, ready: Dict[str, List[Dict[str, Any]]]) -> None:
    label_map = {
        "identity": "Identity",
        "behavior": "Behavior",
        "projects": "Project",
        "constraints": "Constraint",
        "values": "Value",
    }
    rel_map = {
        "identity": "HAS_IDENTITY",
        "behavior": "HAS_BEHAVIOR",
        "projects": "WORKS_ON",
        "constraints": "HAS_CONSTRAINT",
        "values": "HAS_VALUE",
    }

    for category, items in ready.items():
        if not items:
            continue
        label = label_map[category]
        rel = rel_map[category]
        with driver.session(database=database) as session:
            for item in items:
                session.run(
                    f"""
                    MATCH (p:Person {{id: $person_id}})
                    MERGE (n:{label} {{key: $key, value: $value}})
                    MERGE (p)-[:{rel}]->(n)
                    """,
                    person_id=person_id,
                    key=item.get("key"),
                    value=item.get("value"),
                )


# ---------- Pipeline orchestrator ----------
def run_pipeline(conversation: str, use_mock_llm: bool = False, person_id: str = "nandana_dileep") -> Dict[str, Any]:
    load_env()
    uri = env_var("NEO4J_URI")
    user = env_var("NEO4J_USER")
    password = env_var("NEO4J_PASSWORD")
    database = env_var("NEO4J_DATABASE")

    extractions = call_llm_extract(conversation, use_mock=use_mock_llm)
    staging = load_staging()
    staging = update_staging(staging, extractions)
    ready, remaining = split_ready(staging)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    write_ready(driver, database, person_id, ready)
    driver.close()

    save_staging(remaining)
    return {
        "extractions": extractions,
        "ready": ready,
        "staging": remaining,
    }


# ---------- Demo / simple test ----------
if __name__ == "__main__":
    sample_conversation = """
    I'm Nandana, based in Bangalore, building an AI memory app. I love direct, structured replies.
    Evenings are my main build time. Independence matters a lot to me.
    """
    result = run_pipeline(sample_conversation, use_mock_llm=True)
    print("Extractions:", json.dumps(result["extractions"], indent=2))
    print("Ready to write:", json.dumps(result["ready"], indent=2))
    print("Staging now:", json.dumps(result["staging"], indent=2))
