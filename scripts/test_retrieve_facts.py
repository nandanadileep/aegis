"""Unit tests for the unified retrieve_facts function.

Run: python scripts/test_retrieve_facts.py
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def test_retrieve_facts_merges_and_ranks() -> None:
    driver = None
    database = "neo4j"
    person_id = "test"

    direct = [
        {
            "uuid": "d1",
            "source_uuid": "e1",
            "target_uuid": "e2",
            "source_name": "Alice",
            "target_name": "Python",
            "fact": "Alice knows Python",
            "relation_type": "KNOWS",
            "valid_from": None,
            "valid_to": None,
            "created_at": "2026-06-01T00:00:00Z",
            "score": 0.5,
        }
    ]

    related = [
        {
            "uuid": "r1",
            "source_uuid": "e2",
            "target_uuid": "e3",
            "source_name": "Python",
            "target_name": "Project",
            "fact": "Project uses Python",
            "relation_type": "USES",
            "valid_from": None,
            "valid_to": None,
            "created_at": "2026-06-02T00:00:00Z",
            "hop": 1,
        }
    ]

    original_search = gm.search_facts
    original_bfs = gm.bfs_expand
    try:
        gm.search_facts = lambda *a, **kw: direct
        gm.bfs_expand = lambda *a, **kw: related
        results = gm.retrieve_facts(driver, database, person_id, "python", top_k=5)
    finally:
        gm.search_facts = original_search
        gm.bfs_expand = original_bfs

    assert len(results) == 2
    uuids = [r["uuid"] for r in results]
    assert "d1" in uuids
    assert "r1" in uuids
    # Direct hit should outrank BFS-expanded fact.
    assert results[0]["uuid"] == "d1"
    assert results[0]["score"] > results[1]["score"]
    print("PASS: retrieve_facts merges and ranks")


def test_retrieve_facts_empty_query_returns_recent() -> None:
    driver = None
    database = "neo4j"
    person_id = "test"

    recent = [
        {
            "uuid": "recent1",
            "source_name": "Alice",
            "target_name": "Bob",
            "fact": "Alice met Bob",
            "relation_type": "MET",
        }
    ]

    original_recent = gm._fetch_recent_facts
    try:
        gm._fetch_recent_facts = lambda *a, **kw: recent
        results = gm.retrieve_facts(driver, database, person_id, "", top_k=5)
    finally:
        gm._fetch_recent_facts = original_recent

    assert len(results) == 1
    assert results[0]["uuid"] == "recent1"
    print("PASS: retrieve_facts empty query returns recent facts")


if __name__ == "__main__":
    test_retrieve_facts_merges_and_ranks()
    test_retrieve_facts_empty_query_returns_recent()
    print("\nAll retrieve_facts tests passed.")
