"""Unit tests for structured memory ingestion helpers.

Run: python3 scripts/test_structured_ingestion.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def test_parse_structured_entities() -> None:
    entities = gm._parse_structured_entities([
        {"name": "Alice", "type": "Person", "summary": "Founder"},
        {"name": "", "type": "Person"},
        {"name": "Acme", "entity_type": "Organization"},
    ])
    assert len(entities) == 2
    assert entities[0].name == "Alice"
    assert entities[1].entity_type == "Organization"
    print("PASS: parse structured entities")


def test_parse_structured_binary_fact() -> None:
    alice = gm.Entity("Alice", "Person")
    neo4j = gm.Entity("Neo4j", "Technology")
    lookup = gm._entity_lookup_map([alice, neo4j])
    facts = gm._parse_structured_facts([{
        "source": "Alice",
        "target": "Neo4j",
        "relation_type": "USES",
        "fact": "Alice uses Neo4j",
        "valid_from": "2026-01-01T00:00:00Z",
    }], lookup)
    assert len(facts) == 1
    assert facts[0].relation_type == "USES"
    assert facts[0].valid_from == "2026-01-01T00:00:00Z"
    assert not facts[0].is_hyperedge
    print("PASS: parse structured binary fact")


def test_parse_structured_missing_entity_skipped() -> None:
    alice = gm.Entity("Alice", "Person")
    lookup = gm._entity_lookup_map([alice])
    facts = gm._parse_structured_facts([{
        "source": "Alice",
        "target": "Missing",
        "relation_type": "KNOWS",
        "fact": "Unknown",
    }], lookup)
    assert facts == []
    print("PASS: skip facts with unknown entities")


def test_ingest_structured_memory_mocked() -> None:
    created_entities = []
    created_facts = []

    def fake_create_entity(driver, database, person_id, entity, episode_id=None):
        created_entities.append(entity.name)

    def fake_create_fact(driver, database, person_id, fact, episode_id=None):
        created_facts.append(fact)

    original_entity = gm.create_or_update_entity
    original_fact = gm.create_fact
    original_resolve_entities = gm.resolve_entities
    original_resolve_facts = gm.resolve_facts
    original_detect = gm.detect_communities
    original_fetch = gm.fetch_existing_entities
    try:
        gm.create_or_update_entity = fake_create_entity
        gm.create_fact = fake_create_fact
        gm.fetch_existing_entities = lambda *a, **k: []
        gm.resolve_entities = lambda entities, existing, llm_fn=None: (entities, {})
        gm.resolve_facts = lambda *a, **k: k.get("facts") if False else a[3]
        gm.detect_communities = lambda *a, **k: []

        result = gm.ingest_structured_memory(
            None,
            "neo4j",
            "user-1",
            entities_data=[
                {"name": "Alice", "type": "Person"},
                {"name": "Bob", "type": "Person"},
            ],
            facts_data=[{
                "participants": ["Alice", "Bob"],
                "relation_type": "CO_FOUNDED",
                "fact": "Alice and Bob co-founded a startup",
            }],
            episode_id="ep-test",
            resolve_entities_flag=False,
            resolve_facts_flag=False,
            detect_communities_flag=False,
        )
    finally:
        gm.create_or_update_entity = original_entity
        gm.create_fact = original_fact
        gm.resolve_entities = original_resolve_entities
        gm.resolve_facts = original_resolve_facts
        gm.detect_communities = original_detect
        gm.fetch_existing_entities = original_fetch

    assert set(created_entities) == {"Alice", "Bob"}
    assert len(created_facts) == 1
    assert created_facts[0].relation_type == "CO_FOUNDED"
    assert result["episode_id"] == "ep-test"
    assert len(result["facts"]) == 1
    print("PASS: ingest_structured_memory mocked write path")


if __name__ == "__main__":
    test_parse_structured_entities()
    test_parse_structured_binary_fact()
    test_parse_structured_missing_entity_skipped()
    test_ingest_structured_memory_mocked()
    print("\nAll structured ingestion tests passed.")
