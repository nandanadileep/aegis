"""Unit tests for the hybrid temporal extractor in graph_memory.py.

Run: python scripts/test_temporal_extraction.py
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.graph_memory import extract_temporal


def test_temporal_extraction() -> None:
    ref = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)

    cases = [
        # (fact, expected_valid_from, expected_valid_to)
        ("I started my new job two weeks ago", "2026-06-09T12:00:00Z", None),
        ("I used to work at Google", None, "2026-06-23T12:00:00Z"),
        ("I no longer drink coffee", "2026-06-23T12:00:00Z", None),
        ("I will move to Berlin next month", "2026-07-01T09:00:00Z", None),
        ("I lived in Paris until 2020", None, "2020-12-31T00:00:00Z"),
        ("I have been using Neo4j since 2021", "2021-01-01T00:00:00Z", None),
        ("My birthday is on June 23, 1990", "1990-06-23T12:00:00Z", None),
        ("I enjoy hiking", None, None),
        ("I worked at Acme from 2020 to 2022", "2020-01-01T00:00:00Z", "2022-12-31T00:00:00Z"),
        ("My visa is valid to 2025", None, "2025-12-31T00:00:00Z"),
        ("I quit my job in 2020", "2020-01-01T00:00:00Z", None),
    ]

    failures = 0
    for fact, expected_from, expected_to in cases:
        vf, vt = extract_temporal(fact, ref, llm_fn=None)
        if vf != expected_from or vt != expected_to:
            print(f"FAIL: {fact!r}")
            print(f"  expected: from={expected_from}, to={expected_to}")
            print(f"  actual:   from={vf}, to={vt}")
            failures += 1
        else:
            print(f"PASS: {fact!r}")

    if failures:
        print(f"\n{failures} test(s) failed.")
        sys.exit(1)
    print("\nAll tests passed.")


if __name__ == "__main__":
    test_temporal_extraction()
