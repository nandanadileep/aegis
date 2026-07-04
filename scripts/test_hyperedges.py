"""Unit tests for multi-entity hyper-edge facts.

Run: python3 scripts/test_hyperedges.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def test_fact_entity_pairs_binary() -> None:
    alice = gm.Entity("Alice", "Person")
    bob = gm.Entity("Bob", "Person")
    fact = gm.Fact(source=alice, target=bob, relation_type="KNOWS", fact="Alice knows Bob")
    assert not fact.is_hyperedge
    assert fact.entity_pairs() == [(alice, bob)]
    print("PASS: binary fact pairs")


def test_fact_entity_pairs_hyperedge() -> None:
    alice = gm.Entity("Alice", "Person")
    bob = gm.Entity("Bob", "Person")
    acme = gm.Entity("Acme", "Organization")
    fact = gm.Fact(
        participants=[alice, bob, acme],
        relation_type="CO_FOUNDED",
        fact="Alice and Bob co-founded Acme",
    )
    assert fact.is_hyperedge
    pairs = fact.entity_pairs()
    assert len(pairs) == 3
    pair_keys = {tuple(sorted((a.name, b.name))) for a, b in pairs}
    assert pair_keys == {("Acme", "Alice"), ("Acme", "Bob"), ("Alice", "Bob")}
    print("PASS: hyper-edge pairs")


def test_dedupe_hyperedge_facts() -> None:
    rows = [
        {
            "uuid": "f1",
            "source_uuid": "e1",
            "target_uuid": "e2",
            "source_name": "Alice",
            "target_name": "Bob",
            "relation_type": "CO_FOUNDED",
            "fact": "Alice and Bob co-founded Acme",
            "score": 0.4,
        },
        {
            "uuid": "f1",
            "source_uuid": "e1",
            "target_uuid": "e3",
            "source_name": "Alice",
            "target_name": "Acme",
            "relation_type": "CO_FOUNDED",
            "fact": "Alice and Bob co-founded Acme",
            "score": 0.9,
        },
        {
            "uuid": "f1",
            "source_uuid": "e2",
            "target_uuid": "e3",
            "source_name": "Bob",
            "target_name": "Acme",
            "relation_type": "CO_FOUNDED",
            "fact": "Alice and Bob co-founded Acme",
            "score": 0.5,
        },
    ]
    merged = gm._dedupe_hyperedge_facts(rows)
    assert len(merged) == 1
    item = merged[0]
    assert item["is_hyperedge"] is True
    assert set(item["participant_names"]) == {"Alice", "Bob", "Acme"}
    assert item["score"] == 0.9
    print("PASS: dedupe hyper-edge rows")


def test_format_context_hyperedge() -> None:
    text = gm.format_context([{
        "source_name": "Alice",
        "target_name": "Bob",
        "relation_type": "CO_FOUNDED",
        "fact": "Alice and Bob co-founded Acme",
        "is_hyperedge": True,
        "participant_names": ["Acme", "Alice", "Bob"],
    }])
    assert "[Acme, Alice, Bob]" in text
    assert "CO_FOUNDED" in text
    print("PASS: format_context hyper-edge")


def test_parse_structured_hyperedge_fact() -> None:
    alice = gm.Entity("Alice", "Person")
    bob = gm.Entity("Bob", "Person")
    acme = gm.Entity("Acme", "Organization")
    lookup = gm._entity_lookup_map([alice, bob, acme])
    facts = gm._parse_structured_facts([{
        "participants": ["Alice", "Bob", "Acme"],
        "relation_type": "CO_FOUNDED",
        "fact": "Alice and Bob co-founded Acme",
    }], lookup)
    assert len(facts) == 1
    assert facts[0].is_hyperedge
    assert len(facts[0].entity_pairs()) == 3
    print("PASS: parse structured hyper-edge")


if __name__ == "__main__":
    test_fact_entity_pairs_binary()
    test_fact_entity_pairs_hyperedge()
    test_dedupe_hyperedge_facts()
    test_format_context_hyperedge()
    test_parse_structured_hyperedge_fact()
    print("\nAll hyper-edge tests passed.")
