import os
import json
from typing import List, Dict, Any

from flask import Flask, request, jsonify, send_from_directory
from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from scripts.memory_pipeline import run_pipeline
except ImportError:
    from memory_pipeline import run_pipeline


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
           coalesce(n.key, n.name, '') AS key,
           coalesce(n.value, n.name, '') AS value
    """
    driver = get_neo4j_driver()
    with driver.session(database=database) as session:
        data = session.run(query, person_id=person_id).data()
    driver.close()
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
        label_str = labels[0] if labels else ""
        if key and value:
            lines.append(f"- {label_str or rel}: {key} = {value}")
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


def get_groq_client():
    if Groq is None:
        raise RuntimeError("groq package not installed. pip install groq")
    return Groq(api_key=env_var("GROQ_API_KEY"))


# ---------------------------
# Flask app
# ---------------------------
load_env()
app = Flask(__name__, static_folder=".", static_url_path="")

PERSON_ID = os.getenv("PERSON_ID", "nandana_dileep")
DATABASE = env_var("NEO4J_DATABASE")
conversation_history: List[str] = []


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/context", methods=["GET"])
def context():
    records = fetch_memory_summary(PERSON_ID, DATABASE)
    summary = format_memory_context(records)
    return jsonify({"context": summary})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "message required"}), 400

    records = fetch_memory_summary(PERSON_ID, DATABASE)
    memory_context = format_memory_context(records)
    system_prompt = build_system_prompt(memory_context)

    history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    client = get_groq_client()
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=history,
        temperature=0.5,
    )
    reply = completion.choices[0].message.content

    conversation_history.append(f"You: {user_message}")
    conversation_history.append(f"Assistant: {reply}")

    return jsonify({"reply": reply})


@app.route("/save", methods=["POST"])
def save():
    transcript = "\n".join(conversation_history)
    if transcript.strip():
        run_pipeline(transcript, use_mock_llm=False, person_id=PERSON_ID)
        conversation_history.clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
