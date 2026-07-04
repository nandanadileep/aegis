#!/usr/bin/env python3
"""Compare retrieval JSON results across backends and print a summary table."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKENDS = ["flat_rag", "session_summary", "aegis"]


def load_result(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def gold_rank(retrieved: List[str], gold_ids: List[str]) -> Optional[int]:
    """1-based rank of first gold session in retrieved list."""
    for i, sid in enumerate(retrieved, start=1):
        if sid in gold_ids:
            return i
    return None


def compare(results_dir: Path, run_id: str) -> None:
    loaded: Dict[str, Dict[str, Any]] = {}
    for backend in BACKENDS:
        path = results_dir / f"retrieval_{backend}_{run_id}.json"
        data = load_result(path)
        if data:
            loaded[backend] = data
        else:
            print(f"(missing {path.name})")

    if not loaded:
        print("No result files found.")
        return

    question_ids = set()
    rows_by_backend: Dict[str, Dict[str, dict]] = {}
    for backend, data in loaded.items():
        rows = {r["question_id"]: r for r in data.get("questions", [])}
        rows_by_backend[backend] = rows
        question_ids.update(rows.keys())

    active = [b for b in BACKENDS if b in loaded]
    header = "| Question | " + " | ".join(f"{b} rank" for b in active) + " |"
    sep = "|----------|" + "|".join("--------" for _ in active) + "|"
    print("## Retrieval comparison\n")
    print(header)
    print(sep)

    for qid in sorted(question_ids):
        cells = [f"| {qid[:8]}…"]
        gold: List[str] = []
        for backend in active:
            row = rows_by_backend[backend].get(qid, {})
            gold = list(row.get("gold_session_ids") or gold)
            rank = gold_rank(list(row.get("retrieved_session_ids") or []), gold)
            cells.append(str(rank or "-"))
        print(" | ".join(cells) + " |")

    print("\n### Summary\n")
    for backend in active:
        s = loaded[backend].get("summary", {})
        print(
            f"- **{backend}**: recall@10={s.get('recall@10', 0):.3f}, "
            f"ndcg@10={s.get('ndcg@10', 0):.3f}, "
            f"recall@5={s.get('recall@5', 0):.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="dev")
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).parent / "results")
    args = parser.parse_args()
    compare(args.results_dir, args.run_id)


if __name__ == "__main__":
    main()
