import os
from typing import List, Dict, Any

import litellm
from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from scripts.graph_memory import fetch_all_facts, format_context
except ImportError:
    from graph_memory import fetch_all_facts, format_context  # type: ignore


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
def fetch_memory(driver, database: str, person_id: str) -> str:
    """Pull all active ERF facts for the person as a formatted context block."""
    facts = fetch_all_facts(driver, database, person_id)
    return format_context(facts)


# ---------- chat ----------
def chat_loop(memory_context: str, person_id: str) -> None:
    model = os.getenv("LLM_MODEL", "groq/llama-3.3-70b-versatile")
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
        completion = litellm.completion(
            model=model,
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

    driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")
    memory_context = fetch_memory(driver, database, person_id)
    driver.close()

    chat_loop(memory_context, person_id)


if __name__ == "__main__":
    main()
