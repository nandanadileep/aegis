import os
from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def load_env(path: str = ".env") -> None:
    """Load environment variables from a .env file if python-dotenv is available."""
    if load_dotenv is None:
        return
    load_dotenv(path)


def get_env_var(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def main() -> None:
    load_env()

    uri = get_env_var("NEO4J_URI")
    user = get_env_var("NEO4J_USER")
    password = get_env_var("NEO4J_PASSWORD")
    database = get_env_var("NEO4J_DATABASE")

    query = "MATCH (n) RETURN n LIMIT 25"

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session(database=database) as session:
        records = list(session.run(query))

    print(f"Rows: {len(records)}")
    for rec in records:
        node = rec["n"]
        print(node.get("id") or node.get("name") or node)


if __name__ == "__main__":
    main()
