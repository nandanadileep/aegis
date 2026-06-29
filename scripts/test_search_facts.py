"""Unit tests for Neo4j-native search helpers.

Run: python scripts/test_search_facts.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def test_build_fact_search_text() -> None:
    text = gm._build_fact_search_text(
        "Alice",
        "Python",
        "KNOWS",
        "Alice knows Python well.",
    )
    assert "alice" in text
    assert "python" in text
    assert "knows" in text
    print("PASS: build_fact_search_text")


def test_sanitize_fts_query() -> None:
    q = gm._sanitize_fts_query("Python + Neo4j")
    assert "python" in q.lower()
    assert "neo4j" in q.lower()
    assert " AND " in q
    print("PASS: sanitize_fts_query")


def test_search_facts_integration() -> None:
    """End-to-end index search against local Neo4j when available."""
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except Exception:
        pass

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    if not uri or not user or not password:
        print("SKIP: search_facts integration (Neo4j env not set)")
        return

    from neo4j import GraphDatabase

    person_id = "test_search_facts_user"
    driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")
    try:
        gm.ensure_indexes(driver, database)
        with driver.session(database=database) as session:
            session.run(
                "MATCH (p:Person {id: $person_id}) DETACH DELETE p",
                person_id=person_id,
            )
            session.run("MERGE (p:Person {id: $person_id})", person_id=person_id)
            session.run(
                """
                MERGE (a:Entity {uuid: 'e-alice', person_id: $person_id})
                SET a.name = $a_name
                MERGE (b:Entity {uuid: 'e-python', person_id: $person_id})
                SET b.name = $b_name
                CREATE (a)-[f:FACT {
                    uuid: 'f-python',
                    person_id: $person_id,
                    fact: $fact_enc,
                    relation_type: 'KNOWS',
                    search_text: $search_text,
                    created_at: '2026-06-01T00:00:00Z',
                    valid_from: '2026-06-01T00:00:00Z'
                }]->(b)
                """,
                person_id=person_id,
                a_name=gm.enc("Alice", person_id),
                b_name=gm.enc("Python", person_id),
                fact_enc=gm.enc("Alice knows Python", person_id),
                search_text=gm._build_fact_search_text(
                    "Alice", "Python", "KNOWS", "Alice knows Python"
                ),
            )

        results = gm.search_facts(driver, database, person_id, "python", top_k=5)
        assert results, "expected at least one search hit"
        assert results[0]["uuid"] == "f-python"
        print("PASS: search_facts integration")
    finally:
        with driver.session(database=database) as session:
            session.run(
                "MATCH (p:Person {id: $person_id}) DETACH DELETE p",
                person_id=person_id,
            )
        driver.close()


if __name__ == "__main__":
    test_build_fact_search_text()
    test_sanitize_fts_query()
    test_search_facts_integration()
    print("\nAll search_facts tests passed.")
