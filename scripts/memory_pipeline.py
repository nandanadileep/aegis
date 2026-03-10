import json
import os
from urllib.parse import urlparse, urlunparse, quote
from typing import Dict, List, Any, Tuple

from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:  
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:  
    OpenAI = None

try:
    import redis
except ImportError:
    redis = None


THRESHOLDS = {
    "identity": 0.6,
    "behavior": 0.75,
    "projects": 0.65,
    "constraints": 0.7,
    "values": 0.85,
}


def load_env(path: str = ".env") -> None:
    if load_dotenv:
        load_dotenv(path)


def env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


def empty_staging() -> Dict[str, List[Dict[str, Any]]]:
    return {k: [] for k in THRESHOLDS.keys()}


def normalize_redis_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if not host:
        return raw_url

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


def staging_key(person_id: str) -> str:
    return f"staging:{person_id}"


def call_llm_extract(conversation: str, use_mock: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """Return extraction dict keyed by category; each item has key/value/status."""
    if use_mock or not OpenAI:
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

    client = OpenAI(api_key=env_var("OPENAI_API_KEY"))
    prompt = (
        "Extract any new information from the conversation in the five categories. "
        "Return JSON with keys identity, behavior, projects, constraints, values. "
        "Each value is a list of objects with keys: key, value, status "
        "(one of first_mention, confirmation, contradiction, explicit_preference). "
        "Use empty list if nothing new."
    )
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    completion = client.chat.completions.create(
        model=model_name,
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


def load_staging(redis_client, person_id: str) -> Dict[str, List[Dict[str, Any]]]:
    raw = redis_client.get(staging_key(person_id))
    if not raw:
        return empty_staging()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return empty_staging()
    if not isinstance(parsed, dict):
        return empty_staging()

    normalized = empty_staging()
    for category, items in parsed.items():
        if not isinstance(items, list):
            continue
        normalized[category] = items
    return normalized


def save_staging(redis_client, person_id: str, staging: Dict[str, List[Dict[str, Any]]]) -> None:
    redis_client.set(staging_key(person_id), json.dumps(staging))


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


def run_pipeline(conversation: str, use_mock_llm: bool = False, person_id: str = "nandana_dileep", redis_client=None, neo4j_driver=None) -> Dict[str, Any]:
    load_env()
    
    # Use provided clients/drivers or create new ones
    if redis_client is None:
        redis_client = get_redis_client()
    
    if neo4j_driver is None:
        uri = env_var("NEO4J_URI")
        user = env_var("NEO4J_USER")
        password = env_var("NEO4J_PASSWORD")
        neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
        close_driver = True
    else:
        close_driver = False

    try:
        database = env_var("NEO4J_DATABASE")
        extractions = call_llm_extract(conversation, use_mock=use_mock_llm)
        staging = load_staging(redis_client, person_id)
        staging = update_staging(staging, extractions)
        ready, remaining = split_ready(staging)

        write_ready(neo4j_driver, database, person_id, ready)
        save_staging(redis_client, person_id, remaining)
        
        return {
            "extractions": extractions,
            "ready": ready,
            "staging": remaining,
        }
    finally:
        if close_driver:
            neo4j_driver.close()


if __name__ == "__main__":
    sample_conversation = """
    I'm Nandana, based in Bangalore, building an AI memory app. I love direct, structured replies.
    Evenings are my main build time. Independence matters a lot to me.
    """
    result = run_pipeline(sample_conversation, use_mock_llm=True)
    print("Extractions:", json.dumps(result["extractions"], indent=2))
    print("Ready to write:", json.dumps(result["ready"], indent=2))
    print("Staging now:", json.dumps(result["staging"], indent=2))
