"""Unit tests for community detection helpers.

Run: python scripts/test_community_detection.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.graph_memory import _connected_components, _split_large_component


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


if __name__ == "__main__":
    test_connected_components()
    test_split_large_component()
    print("\nAll community-detection tests passed.")
