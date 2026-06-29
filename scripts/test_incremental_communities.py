"""Integration tests for incremental community detection.

Run: python scripts/test_incremental_communities.py
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def _mock_llm_fn(**kwargs: Any) -> Any:
    class _Resp:
        class _Choice:
            class _Msg:
                content = '[{"name": "Test Cluster", "summary": "Test summary."}]'
            message = _Msg()
        choices = [_Choice()]
    return _Resp()


def test_incremental_community_update() -> None:
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
        print("SKIP: incremental community integration (Neo4j env not set)")
        return

    from neo4j import GraphDatabase

    person_id = "test_incremental_communities_user"
    driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")

    episode_id = "inc-ep1"

    def cleanup(session) -> None:
        session.run(
            """
            MATCH (ep:Episode {id: $episode_id})
            DETACH DELETE ep
            """,
            episode_id=episode_id,
        )
        session.run(
            """
            MATCH (p:Person {id: $person_id})
            OPTIONAL MATCH (p)-[:HAS_COMMUNITY]->(c:Community)
            OPTIONAL MATCH (ep:Episode {person_id: $person_id})
            DETACH DELETE c, ep, p
            WITH count(*) AS _
            MATCH (e:Entity {person_id: $person_id})
            DETACH DELETE e
            """,
            person_id=person_id,
        )

    try:
        gm.ensure_indexes(driver, database)
        with driver.session(database=database) as session:
            cleanup(session)
            session.run("MERGE (p:Person {id: $person_id})", person_id=person_id)
            session.run(
                """
                MERGE (a:Entity {uuid: 'inc-a', person_id: $person_id})
                SET a.name = $a_name
                MERGE (b:Entity {uuid: 'inc-b', person_id: $person_id})
                SET b.name = $b_name
                CREATE (a)-[f:FACT {
                    uuid: 'inc-f1',
                    person_id: $person_id,
                    fact: $fact_enc,
                    relation_type: 'KNOWS',
                    search_text: 'alice knows bob',
                    created_at: '2026-06-01T00:00:00Z',
                    valid_from: '2026-06-01T00:00:00Z'
                }]->(b)
                """,
                person_id=person_id,
                a_name=gm.enc("Alice", person_id),
                b_name=gm.enc("Bob", person_id),
                fact_enc=gm.enc("Alice knows Bob", person_id),
            )

        full = gm.detect_communities(
            driver,
            database,
            person_id,
            llm_fn=_mock_llm_fn,
            embed_fn=lambda texts: [],
        )
        assert len(full) == 1
        original_uuid = full[0]["uuid"]

        with driver.session(database=database) as session:
            session.run(
                """
                MERGE (c:Entity {uuid: 'inc-c', person_id: $person_id})
                SET c.name = $c_name
                WITH c
                MATCH (a:Entity {uuid: 'inc-a', person_id: $person_id})
                CREATE (a)-[f:FACT {
                    uuid: 'inc-f2',
                    person_id: $person_id,
                    fact: $fact_enc,
                    relation_type: 'WORKS_AT',
                    search_text: 'alice works at acme',
                    created_at: '2026-06-02T00:00:00Z',
                    valid_from: '2026-06-02T00:00:00Z'
                }]->(c)
                CREATE (ep:Episode {
                    id: $episode_id,
                    person_id: $person_id,
                    body: 'Alice works at Acme',
                    source: 'test',
                    created_at: '2026-06-02T00:00:00Z'
                })
                MERGE (c)-[:MENTIONED_IN]->(ep)
                MERGE (a)-[:MENTIONED_IN]->(ep)
                """,
                person_id=person_id,
                episode_id=episode_id,
                c_name=gm.enc("Acme", person_id),
                fact_enc=gm.enc("Alice works at Acme", person_id),
            )

        updated = gm.detect_communities(
            driver,
            database,
            person_id,
            llm_fn=_mock_llm_fn,
            embed_fn=lambda texts: [],
            episode_id=episode_id,
            touched_entity_uuids=["inc-a", "inc-c"],
        )
        assert updated, "expected incremental communities"

        all_communities = gm.fetch_communities(driver, database, person_id)
        all_uuids = {c["uuid"] for c in all_communities}
        assert original_uuid not in all_uuids, "full-rebuild community should be replaced"
        assert len(all_uuids) >= 1

        untouched = gm.fetch_communities(driver, database, person_id, limit=100)
        entity_sets = {tuple(sorted(c.get("entity_uuids") or [])) for c in untouched}
        assert any("inc-b" in group for group in entity_sets) or len(updated) >= 2
        print("PASS: incremental community update")
    finally:
        with driver.session(database=database) as session:
            cleanup(session)
        driver.close()


if __name__ == "__main__":
    test_incremental_community_update()
    print("\nAll incremental community tests passed.")
