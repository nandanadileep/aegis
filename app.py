import os
import json
from urllib.parse import urlparse, urlunparse, quote
from typing import List, Dict, Any, Optional
from pathlib import Path

import litellm
from flask import Flask, request, jsonify, send_from_directory, Response
from neo4j import GraphDatabase

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
    return dict(row)


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
        f"# Digital Twin — {person_name}",
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
        f"*Twin Card generated by Aegis · {person_id}*",
    ]

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


@app.route("/api/wallet", methods=["GET"])
def export_wallet():
    person_id = resolve_person_id()
    md = generate_wallet_markdown(person_id, DATABASE)
    filename = f"aegis_wallet_{person_id}.md"
    return Response(
        md,
        mimetype="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

    completion = litellm.completion(
        model=LLM_MODEL,
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

    completion = litellm.completion(
        model=model,
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


@app.route("/memory")
def memory_page():
    return send_from_directory(app.static_folder, "memory.html")


@app.route("/onboarding")
def onboarding_page():
    return send_from_directory(app.static_folder, "onboarding.html")


@app.route("/api/import", methods=["POST"])
def import_twin():
    data = parse_body_json()
    person_id = resolve_person_id(data)
    twin = data.get("twin", {})
    if not isinstance(twin, dict):
        return jsonify({"error": "twin must be a JSON object"}), 400

    name = str(twin.get("name") or person_id)
    description = str(twin.get("twin_description") or "")
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
                    p.description = $desc,
                    p.speaking_style = $style
                """,
                pid=person_id, name=name, desc=description, style=speaking_style,
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
                        MERGE (n:{label} {{name: $name}})
                        MERGE (p)-[:{rel}]->(n)
                        """,
                        pid=person_id, name=item,
                    )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "person_id": person_id})


@app.route("/api/onboard", methods=["POST"])
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
def get_graph():
    """Fetch all nodes and relationships for a person."""
    person_id = resolve_person_id()
    
    query = """
    MATCH (p:Person {id: $person_id})
    MATCH (p)-[*1..10]-(n)
    WHERE n <> p
    RETURN DISTINCT id(n) as node_id, n.name as name, n.key as key, labels(n) as labels
    """
    
    query_edges = """
    MATCH (p:Person {id: $person_id})
    MATCH (p)-[*1..10]-(n)
    MATCH (n)-[r]-(m)
    WHERE n <> p AND m <> p
    RETURN id(r) as rel_id, id(n) as from_id, id(m) as to_id, type(r) as rel_type
    """
    
    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            nodes_result = session.run(query, person_id=person_id).data()
            edges_result = session.run(query_edges, person_id=person_id).data()
        
        nodes_dict = {}
        
        for record in nodes_result:
            node_id = str(record["node_id"])
            name = record.get("name") or record.get("key") or "Node"
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
def create_node():
    """Create a new node."""
    person_id = resolve_person_id()
    data = parse_body_json()
    
    label = data.get("label", "").strip()
    name = data.get("name", "").strip()
    properties = data.get("properties", {})
    
    if not label or not name:
        return jsonify({"error": "label and name required"}), 400
    
    try:
        with NEO4J_DRIVER.session(database=DATABASE) as session:
            # Create the node
            query = f"""
            CREATE (n:{label} {{name: $name, key: $name}})
            SET n += $properties
            RETURN id(n) as node_id
            """
            result = session.run(query, name=name, properties=properties)
            node_id = result.single()["node_id"]
            
            # Connect to Person node
            rel_query = """
            MATCH (p:Person {id: $person_id})
            MATCH (n)
            WHERE id(n) = $node_id
            CREATE (p)-[:KNOWS]->(n)
            """
            session.run(rel_query, person_id=person_id, node_id=node_id)
        
        return jsonify({"id": str(node_id), "label": label, "name": name})
    except Exception as e:
        return jsonify({"error": str(e), "detail": str(e)}), 500


@app.route("/api/relationships", methods=["POST"])
def create_relationship():
    """Create a new relationship between nodes."""
    person_id = resolve_person_id()
    data = parse_body_json()
    
    from_id = data.get("from")
    rel_type = data.get("type", "").strip().upper()
    to_id = data.get("to")
    
    if not from_id or not rel_type or not to_id:
        return jsonify({"error": "from, type, and to required"}), 400
    
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
