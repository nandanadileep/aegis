"""Unit tests for bi-temporal provenance and episode lineage formatting.

Run: python scripts/test_bitemporal.py
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def test_resolve_as_of_prefers_as_of() -> None:
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert gm._resolve_as_of(current_time=t1, as_of=t2) == t2
    assert gm._resolve_as_of(current_time=t1) == t1
    resolved = gm._resolve_as_of()
    assert resolved.tzinfo is not None
    print("PASS: _resolve_as_of")


def test_fact_validity_pred_includes_transaction_time() -> None:
    pred = gm._fact_validity_pred("f")
    assert "ingested_at" in pred
    assert "created_at" in pred
    assert "expired_at > $now" in pred
    inline = gm._fact_as_of_pred_inline("f")
    assert "ingested_at" in inline
    assert "created_at" in inline
    print("PASS: bi-temporal predicates")


def test_format_context_episode_lineage_off_by_default() -> None:
    facts = [{
        "source_name": "Alice",
        "target_name": "Bob",
        "relation_type": "KNOWS",
        "fact": "Alice knows Bob",
        "source_episode_id": "ep-123",
        "ingested_at": "2026-06-01T12:00:00Z",
        "created_at": "2026-06-01T12:00:00Z",
    }]
    text = gm.format_context(facts)
    assert "ep-123" not in text
    assert "ingested:" not in text
    print("PASS: format_context hides lineage by default")


def test_format_context_episode_lineage_on() -> None:
    facts = [{
        "source_name": "Alice",
        "target_name": "Bob",
        "relation_type": "KNOWS",
        "fact": "Alice knows Bob",
        "source_episode_id": "ep-123",
        "ingested_at": "2026-06-01T12:00:00Z",
        "created_at": "2026-06-01T12:00:00Z",
    }]
    text = gm.format_context(facts, include_episode_lineage=True)
    assert "episode: ep-123" in text
    assert "ingested: 2026-06-01T12:00:00Z" in text
    assert "recorded: 2026-06-01T12:00:00Z" in text
    print("PASS: format_context shows lineage when enabled")


def test_retrieve_facts_passes_as_of() -> None:
    """Verify retrieve_facts resolves as_of and forwards to search_facts."""
    captured: dict = {}

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return []

    original = gm.search_facts
    try:
        gm.search_facts = fake_search
        gm.search_communities = lambda *a, **kw: []
        as_of = datetime(2025, 3, 15, tzinfo=timezone.utc)
        gm.retrieve_facts(None, "neo4j", "test", "query", as_of=as_of)
        assert captured.get("as_of") == as_of
    finally:
        gm.search_facts = original
    print("PASS: retrieve_facts forwards as_of")


if __name__ == "__main__":
    test_resolve_as_of_prefers_as_of()
    test_fact_validity_pred_includes_transaction_time()
    test_format_context_episode_lineage_off_by_default()
    test_format_context_episode_lineage_on()
    test_retrieve_facts_passes_as_of()
    print("\nAll bi-temporal tests passed.")
