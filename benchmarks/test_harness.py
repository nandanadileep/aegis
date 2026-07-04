"""Unit tests for benchmark metrics and flat RAG backend."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.backends.flat_rag import FlatRAGBackend
from benchmarks.data_format import parse_question_date, truncate_session_transcript
from benchmarks.metrics import session_ndcg_at_k, session_recall_at_k


def test_format_zep_context() -> None:
    from scripts import graph_memory as gm

    text = gm.format_zep_context(
        [{
            "source_name": "Alice",
            "target_name": "MIT",
            "relation_type": "STUDIED_AT",
            "fact": "graduated with Business Administration",
            "valid_from": "2020-01-01",
            "valid_to": None,
        }],
        [{"name": "Alice", "summary": "Software engineer in Boston"}],
    )
    assert "<FACTS>" in text and "<ENTITIES>" in text
    assert "Business Administration" in text
    assert "Alice: Software engineer" in text
    print("PASS: format_zep_context")


def test_parse_question_date_longmemeval() -> None:
    dt = parse_question_date("2023/05/30 (Tue) 17:27")
    assert dt is not None
    assert dt.year == 2023 and dt.month == 5 and dt.day == 30
    print("PASS: parse_question_date_longmemeval")


def test_truncate_session_preserves_user_turns() -> None:
    turns = [
        {"role": "assistant", "content": "x" * 5000},
        {"role": "user", "content": "I graduated with a degree in Business Administration."},
        {"role": "assistant", "content": "y" * 5000},
    ]
    text = truncate_session_transcript(turns, max_chars=8000)
    assert "Business Administration" in text
    print("PASS: truncate_session_preserves_user_turns")


def test_session_recall_at_k() -> None:
    retrieved = ["s3", "s1", "s2"]
    gold = ["s1"]
    assert session_recall_at_k(retrieved, gold, 1) == 0.0
    assert session_recall_at_k(retrieved, gold, 2) == 1.0
    print("PASS: session_recall_at_k")


def test_flat_rag_retrieval() -> None:
    backend = FlatRAGBackend()
    instance_id = "q1"
    backend.insert_session(
        instance_id,
        "session-a",
        [{"role": "user", "content": "I adopted a golden retriever named Max in Portland."}],
    )
    backend.insert_session(
        instance_id,
        "session-b",
        [{"role": "user", "content": "My favorite coffee shop is on Main Street."}],
    )
    result = backend.retrieve(instance_id, "golden retriever Max", top_k=5)
    assert "session-a" in result.session_ids
    assert "Max" in result.context_text
    print("PASS: flat_rag retrieval")


def test_session_summary_retrieval() -> None:
    from benchmarks.backends.session_summary_rag import SessionSummaryRAGBackend

    backend = SessionSummaryRAGBackend()
    instance_id = "q1"
    backend._summaries[instance_id] = {
        "session-a": "User adopted a golden retriever named Max in Portland.",
        "session-b": "User likes coffee on Main Street.",
    }
    result = backend.retrieve(instance_id, "golden retriever Max", top_k=5)
    assert "session-a" in result.session_ids
    assert "Max" in result.context_text
    print("PASS: session_summary retrieval")


if __name__ == "__main__":
    test_format_zep_context()
    test_parse_question_date_longmemeval()
    test_session_recall_at_k()
    test_truncate_session_preserves_user_turns()
    test_flat_rag_retrieval()
    test_session_summary_retrieval()
    print("\nAll benchmark unit tests passed.")
