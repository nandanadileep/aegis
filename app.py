import os
import json
from urllib.parse import urlparse, urlunparse, quote
from typing import List, Dict, Any, Optional

from flask import Flask, request, jsonify, send_from_directory
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

try:
    from scripts.memory_pipeline import run_pipeline
except ImportError:
    from memory_pipeline import run_pipeline

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# ---------------------------
# Helpers
# ---------------------------
def load_env(path: str = ".env") -> None:
    if load_dotenv:
        load_dotenv(path)


def env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val




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
    return data


def format_memory_context(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "No stored memory yet."
    lines = []
    for rec in records:
        rel = rec.get("rel", "")
        labels = rec.get("labels", [])
        key = rec.get("key", "")
        value = rec.get("value", "")
        props = rec.get("props") or {}
        label_str = labels[0] if labels else ""
        if key and value:
            lines.append(f"- {label_str or rel}: {key} = {value}")
        elif props:
            details = []
            for prop_key in sorted(props.keys()):
                prop_value = props[prop_key]
                if isinstance(prop_value, list):
                    rendered = ", ".join(str(v) for v in prop_value)
                else:
                    rendered = str(prop_value)
                details.append(f"{prop_key} = {rendered}")
            lines.append(f"- {label_str or rel}: {'; '.join(details)}")
        else:
            lines.append(f"- {label_str or rel}: {value}")
    return "\n".join(lines)


def build_system_prompt(memory_context: str) -> str:
    return f"""
You are a personalized AI assistant.
You already know this person well.
Here is their memory profile:

{memory_context}

Instructions:
- Use this context to shape your responses naturally
- Never say "I know that you..." or reference the memory directly
- Adapt your tone, depth, and examples to who they are
- If they mention something new about themselves, note it
- If something contradicts their profile, trust what they say now over stored memory
- Respond like a brilliant friend who knows them well, not like a system reading a file
""".strip()


def get_openai_client():
    if OpenAI is None:
        raise RuntimeError("openai package not installed. pip install openai")
    return OpenAI(api_key=env_var("OPENAI_API_KEY"))


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
    if payload:
        payload_person_id = payload.get("person_id")
        if payload_person_id is not None:
            candidate = str(payload_person_id).strip()
            if candidate:
                return candidate

    header_person_id = request.headers.get("X-Person-Id", "").strip()
    if header_person_id:
        return header_person_id

    query_person_id = request.args.get("person_id", "").strip()
    if query_person_id:
        return query_person_id

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
app = Flask(__name__, static_folder=".", static_url_path="")

DEFAULT_PERSON_ID = os.getenv("PERSON_ID", "nandana_dileep")
DATABASE = env_var("NEO4J_DATABASE")
REDIS_CLIENT = get_redis_client()
NEO4J_DRIVER = get_neo4j_driver()


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/context", methods=["GET"])
def context():
    person_id = resolve_person_id()
    records = fetch_memory_summary(person_id, DATABASE)
    summary = format_memory_context(records)
    return jsonify({"context": summary})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "invalid payload"}), 400

    user_message = str(data.get("message", "")).strip()
    if not user_message:
        return jsonify({"error": "message required"}), 400

    person_id = resolve_person_id(data)

    try:
        records = fetch_memory_summary(person_id, DATABASE)
    except Exception as e:
        return jsonify({"error": "memory unavailable", "detail": str(e)}), 503

    memory_context = format_memory_context(records)
    system_prompt = build_system_prompt(memory_context)

    storage_warning = None
    try:
        conversation_history = load_conversation_history(person_id)
    except Exception as e:
        conversation_history = []
        storage_warning = f"redis read failed: {e}"
    history = [{"role": "system", "content": system_prompt}, *conversation_history]
    history.append({"role": "user", "content": user_message})

    client = get_openai_client()
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=history,
        temperature=0.5,
    )
    reply = completion.choices[0].message.content or ""

    try:
        append_conversation_message(person_id, "user", user_message)
        append_conversation_message(person_id, "assistant", reply)
    except Exception as e:
        if storage_warning:
            storage_warning = f"{storage_warning}; redis write failed: {e}"
        else:
            storage_warning = f"redis write failed: {e}"

    response: Dict[str, Any] = {"reply": reply}
    if storage_warning:
        response["warning"] = storage_warning
    return jsonify(response)


@app.route("/save", methods=["POST"])
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
