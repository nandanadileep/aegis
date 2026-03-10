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
           properties(n) AS props,
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


# ---------- groq chat ----------
def chat_loop(memory_context: str, person_id: str) -> None:
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
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history,
            temperature=0.5,
        )
        reply = completion.choices[0].message.content
        print(f"Assistant: {reply}")
        history.append({"role": "assistant", "content": reply})


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
    chat_loop(memory_context, person_id)


if __name__ == "__main__":
    main()
