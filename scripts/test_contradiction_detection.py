"""Unit tests for contradiction / duplicate detection helpers.

Run: python scripts/test_contradiction_detection.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.graph_memory import (
    Entity,
    Fact,
    _facts_temporally_overlap,
    _is_heuristic_contradiction,
    _is_heuristic_duplicate,
)


def _fact(text: str, relation_type: str = "USES") -> Fact:
    a = Entity(name="Alice", entity_type="Person", summary="")
    b = Entity(name="Bob", entity_type="Person", summary="")
    return Fact(
        source=a,
        target=b,
        relation_type=relation_type,
        fact=text,
    )


def _old(fact: str, relation_type: str = "USES", vf: str | None = None, vt: str | None = None) -> dict:
    return {
        "uuid": "old-1",
        "fact": fact,
        "relation_type": relation_type,
        "valid_from": vf,
        "valid_to": vt,
    }


def test_temporal_overlap() -> None:
    assert _facts_temporally_overlap("2024-01-01T00:00:00Z", None, "2023-01-01T00:00:00Z", None) is True
    assert _facts_temporally_overlap("2022-01-01T00:00:00Z", "2022-12-31T00:00:00Z",
                                     "2023-01-01T00:00:00Z", "2023-12-31T00:00:00Z") is False
    assert _facts_temporally_overlap(None, None, "2020-01-01T00:00:00Z", "2020-12-31T00:00:00Z") is True
    assert _facts_temporally_overlap("2024-06-01T00:00:00Z", "2024-12-31T00:00:00Z",
                                     "2024-01-01T00:00:00Z", "2024-06-15T00:00:00Z") is True
    print("PASS: temporal overlap")


def test_heuristic_duplicate() -> None:
    assert _is_heuristic_duplicate(_fact("Alice knows Python", "KNOWS"), _old("Alice knows Python", "KNOWS")) is True
    assert _is_heuristic_duplicate(_fact("Alice knows Python", "KNOWS"), _old("Alice knows Java", "KNOWS")) is False
    print("PASS: heuristic duplicate")


def test_heuristic_contradiction() -> None:
    assert _is_heuristic_contradiction(
        _fact("Alice no longer uses Neo4j"),
        _old("Alice uses Neo4j for the app"),
    ) is True
    assert _is_heuristic_contradiction(
        _fact("Alice stopped smoking"),
        _old("Alice smokes"),
    ) is True
    assert _is_heuristic_contradiction(
        _fact("Alice uses Neo4j"),
        _old("Alice uses Neo4j"),
    ) is False
    print("PASS: heuristic contradiction")


if __name__ == "__main__":
    test_temporal_overlap()
    test_heuristic_duplicate()
    test_heuristic_contradiction()
    print("\nAll contradiction-detection tests passed.")
