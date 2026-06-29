"""Integration tests for community-aware retrieval.

Run: python scripts/test_community_retrieval.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def test_community_search_integration() -> None:
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
        print("SKIP: community search integration (Neo4j env not set)")
        return

    from neo4j import GraphDatabase

    person_id = "test_community_retrieval_user"
    entity_a = "e-alice-comm-retrieval"
    entity_b = "e-google-comm-retrieval"
    fact_uuid = "f-work-comm-retrieval"
    community_uuid = "c-work-comm-retrieval"
    driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")
    try:
        gm.ensure_indexes(driver, database)
        with driver.session(database=database) as session:
            session.run(
                """
                MATCH (p:Person {id: $person_id})
                OPTIONAL MATCH (p)-[:HAS_COMMUNITY]->(c:Community)
                DETACH DELETE c, p
                WITH count(*) AS _
                MATCH (e:Entity {person_id: $person_id})
                DETACH DELETE e
                """,
                person_id=person_id,
            )
            session.run("MERGE (p:Person {id: $person_id})", person_id=person_id)
            session.run(
                """
                MERGE (a:Entity {uuid: $entity_a, person_id: $person_id})
                SET a.name = $a_name
                MERGE (b:Entity {uuid: $entity_b, person_id: $person_id})
                SET b.name = $b_name
                CREATE (a)-[f:FACT {
                    uuid: $fact_uuid,
                    person_id: $person_id,
                    fact: $fact_enc,
                    relation_type: 'WORKS_FOR',
                    search_text: $search_text,
                    created_at: '2026-06-01T00:00:00Z',
                    valid_from: '2026-06-01T00:00:00Z'
                }]->(b)
                MERGE (c:Community {
                    uuid: $community_uuid,
                    person_id: $person_id
                })
                SET c.name = 'Work & Career',
                    c.summary = $summary_enc,
                    c.search_text = $community_search_text,
                    c.updated_at = '2026-06-01T00:00:00Z'
                MERGE (p:Person {id: $person_id})-[:HAS_COMMUNITY]->(c)
                MERGE (a)-[:BELONGS_TO]->(c)
                MERGE (b)-[:BELONGS_TO]->(c)
                """,
                person_id=person_id,
                entity_a=entity_a,
                entity_b=entity_b,
                fact_uuid=fact_uuid,
                community_uuid=community_uuid,
                a_name=gm.enc("Alice", person_id),
                b_name=gm.enc("Google", person_id),
                fact_enc=gm.enc("Alice works at Google", person_id),
                search_text=gm._build_fact_search_text(
                    "Alice", "Google", "WORKS_FOR", "Alice works at Google"
                ),
                summary_enc=gm.enc("Alice's professional life and current employer.", person_id),
                community_search_text=gm._build_community_search_text(
                    "Work & Career",
                    "Alice's professional life and current employer.",
                ),
            )

        communities = gm.search_communities(
            driver, database, person_id, "career work", top_k=3
        )
        assert communities, "expected community match"
        assert communities[0]["uuid"] == community_uuid

        results = gm.retrieve_facts(driver, database, person_id, "career", top_k=5)
        assert results, "expected facts from community expansion"
        assert any(r["uuid"] == fact_uuid for r in results)
        print("PASS: community search integration")
    finally:
        with driver.session(database=database) as session:
            session.run(
                """
                MATCH (p:Person {id: $person_id})
                OPTIONAL MATCH (p)-[:HAS_COMMUNITY]->(c:Community)
                DETACH DELETE c, p
                WITH count(*) AS _
                MATCH (e:Entity {person_id: $person_id})
                DETACH DELETE e
                """,
                person_id=person_id,
            )
        driver.close()


if __name__ == "__main__":
    test_community_search_integration()
    print("\nAll community retrieval tests passed.")
