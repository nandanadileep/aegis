"""Unit tests for community detection helpers.

Run: python scripts/test_community_detection.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.graph_memory import (
    _collect_incremental_affected_scope,
    _connected_components,
    _split_large_component,
)


def test_connected_components() -> None:
    entities = [
        {"uuid": "a"},
        {"uuid": "b"},
        {"uuid": "c"},
        {"uuid": "d"},
    ]
    facts = [
        {"source_uuid": "a", "target_uuid": "b"},
        {"source_uuid": "b", "target_uuid": "a"},
        {"source_uuid": "c", "target_uuid": "d"},
    ]
    components = _connected_components(entities, facts)
    assert len(components) == 2
    assert {"a", "b"} in components
    assert {"c", "d"} in components
    print("PASS: connected components")


def test_split_large_component() -> None:
    component = {"a", "b", "c", "d"}
    embeddings = {
        "a": [1.0, 0.0],
        "b": [0.9, 0.1],
        "c": [0.0, 1.0],
        "d": [0.1, 0.9],
    }
    clusters = _split_large_component(component, embeddings, max_size=2, merge_threshold=0.8)
    # With two clear clusters and max_size=2, we expect {a,b} and {c,d}.
    assert len(clusters) == 2
    flat = [sorted(list(c)) for c in clusters]
    assert ["a", "b"] in flat or ["b", "a"] in flat
    assert ["c", "d"] in flat or ["d", "c"] in flat
    print("PASS: split large component")


def test_incremental_affected_scope() -> None:
    entity_to_communities = {
        "x": {"c1"},
        "y": {"c2"},
        "z": {"c2"},
    }
    community_members = {
        "c1": {"x", "a"},
        "c2": {"y", "z", "b"},
    }
    affected_entities, affected_communities = _collect_incremental_affected_scope(
        seed_entity_uuids={"x"},
        neighbor_entity_uuids={"y"},
        entity_to_communities=entity_to_communities,
        community_members=community_members,
    )
    assert affected_communities == {"c1", "c2"}
    assert affected_entities == {"x", "a", "y", "z", "b"}
    print("PASS: incremental affected scope")


def test_incremental_new_entity_scope() -> None:
    affected_entities, affected_communities = _collect_incremental_affected_scope(
        seed_entity_uuids={"new1"},
        neighbor_entity_uuids={"new2"},
        entity_to_communities={},
        community_members={},
    )
    assert affected_communities == set()
    assert affected_entities == {"new1", "new2"}
    print("PASS: incremental new entity scope")


if __name__ == "__main__":
    test_connected_components()
    test_split_large_component()
    test_incremental_affected_scope()
    test_incremental_new_entity_scope()
    print("\nAll community-detection tests passed.")
