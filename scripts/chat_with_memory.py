"""
Interactive chat loop that injects memory from Neo4j into the system prompt
and uses Groq (llama-3.3-70b-versatile) to reply as a personalized assistant.

Usage:
    python3 scripts/chat_with_memory.py

Requirements:
    - .env with GROQ_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE
    - Person node id defaults to "nandana_dileep" (override with PERSON_ID env)
"""

import os
from typing import List, Dict, Any

from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:  # optional
    load_dotenv = None

try:
    from groq import Groq
except ImportError:
    Groq = None

# local pipeline import
try:
    from memory_pipeline import run_pipeline
except ImportError:
    from scripts.memory_pipeline import run_pipeline


# ---------- env helpers ----------
def load_env(path: str = ".env") -> None:
    if load_dotenv:
        load_dotenv(path)


def env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


# ---------- neo4j helpers ----------
def fetch_memory(driver, database: str, person_id: str) -> List[Dict[str, Any]]:
    """
    Pull all outgoing facts from the person into a flat list of dicts.
    Expected node properties: key/value or name.
    """
    query = """
    MATCH (p:Person {id: $person_id})-[r]->(n)
    RETURN type(r) AS rel, labels(n) AS labels,
           coalesce(n.key, n.name, '') AS key,
           coalesce(n.value, n.name, '') AS value
    """
    with driver.session(database=database) as session:
        records = session.run(query, person_id=person_id).data()
    return records


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


# ---------- groq chat ----------
def chat_loop(memory_context: str, person_id: str) -> str:
    if Groq is None:
        raise RuntimeError("groq package not installed. pip install groq")
    client = Groq(api_key=env_var("GROQ_API_KEY"))
    system_prompt = f"""
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

    history = [{"role": "system", "content": system_prompt}]
    transcript: list[str] = []
    print("Chat ready. Type /exit to quit.")
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if user_input.lower() in {"/exit", "exit", "quit"}:
            print("Bye.")
            break
        history.append({"role": "user", "content": user_input})
        transcript.append(f"You: {user_input}")
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history,
            temperature=0.5,
        )
        reply = completion.choices[0].message.content
        print(f"Assistant: {reply}")
        history.append({"role": "assistant", "content": reply})
        transcript.append(f"Assistant: {reply}")

    return "\n".join(transcript)


# ---------- entrypoint ----------
def main() -> None:
    load_env()
    uri = env_var("NEO4J_URI")
    user = env_var("NEO4J_USER")
    password = env_var("NEO4J_PASSWORD")
    database = env_var("NEO4J_DATABASE")
    person_id = os.getenv("PERSON_ID", "nandana_dileep")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    records = fetch_memory(driver, database, person_id)
    driver.close()

    memory_context = format_memory_context(records)
    transcript = chat_loop(memory_context, person_id)

    # After chat ends, run the memory pipeline on the full transcript
    if transcript.strip():
        run_pipeline(transcript, use_mock_llm=False, person_id=person_id)


if __name__ == "__main__":
    main()
