"""Unit tests for episodic extraction context helpers.

Run: python scripts/test_episodic_context.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.graph_memory as gm


def test_format_episodic_context_limits_turns() -> None:
    history = [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "reply 1"},
        {"role": "user", "content": "turn 2"},
        {"role": "assistant", "content": "reply 2"},
        {"role": "user", "content": "turn 3"},
        {"role": "assistant", "content": "reply 3"},
    ]
    text = gm.format_episodic_context(history, max_turns=2)
    assert "turn 1" not in text
    assert "turn 2" in text
    assert "turn 3" in text
    print("PASS: format_episodic_context limits turns")


def test_run_graph_pipeline_forwards_previous_messages() -> None:
    seen: dict = {}

    def fake_entities(current_message: str, previous_messages: str = "", **kw):
        seen["entities"] = (current_message, previous_messages)
        return []

    original_entities = gm.extract_entities
    try:
        gm.extract_entities = fake_entities
        gm.run_graph_pipeline(
            conversation="User: I quit there.",
            person_id="test",
            driver=None,
            database="neo4j",
            previous_messages="User: I work at Google.\nAssistant: Nice.",
        )
    finally:
        gm.extract_entities = original_entities

    assert seen["entities"] == (
        "User: I quit there.",
        "User: I work at Google.\nAssistant: Nice.",
    )
    print("PASS: run_graph_pipeline forwards previous_messages")


if __name__ == "__main__":
    test_format_episodic_context_limits_turns()
    test_run_graph_pipeline_forwards_previous_messages()
    print("\nAll episodic context tests passed.")
