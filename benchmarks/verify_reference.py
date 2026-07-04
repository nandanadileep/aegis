#!/usr/bin/env python3
"""Compare a local benchmark run against committed reference numbers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REFERENCE_DIR = Path(__file__).parent / "reference"
RESULTS_DIR = Path(__file__).parent / "results"

# Retrieval metrics should match closely; QA may drift slightly with LLM judge variance.
TOLERANCE = {
    "recall@5": 0.05,
    "recall@10": 0.05,
    "ndcg@10": 0.10,
    "qa_accuracy": 0.15,
}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def compare_summary(
    label: str,
    ref: Dict[str, Any],
    got: Dict[str, Any],
    keys: List[str],
) -> Tuple[bool, List[str]]:
    ok = True
    lines: List[str] = []
    for key in keys:
        ref_val = float(ref.get(key, 0))
        got_val = float(got.get(key, 0))
        tol = TOLERANCE.get(key, 0.05)
        delta = abs(ref_val - got_val)
        match = delta <= tol
        ok = ok and match
        mark = "OK" if match else "DIFF"
        lines.append(
            f"  [{mark}] {label} {key}: ref={ref_val:.3f} got={got_val:.3f} (Δ={delta:.3f}, tol={tol})"
        )
    return ok, lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify benchmark run vs reference/")
    parser.add_argument("--run-id", default="dev")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=RESULTS_DIR,
        help="Directory with your run output (default: benchmarks/results/)",
    )
    args = parser.parse_args()

    pairs = [
        ("retrieval_flat_rag", ["recall@5", "recall@10", "ndcg@10"]),
        ("retrieval_aegis", ["recall@5", "recall@10", "ndcg@10"]),
        ("qa_flat_rag", ["qa_accuracy", "recall@10"]),
        ("qa_aegis", ["qa_accuracy", "recall@10"]),
    ]

    all_ok = True
    print(f"Comparing {args.results_dir}/*_{args.run_id}.json vs {REFERENCE_DIR}/\n")

    for stem, keys in pairs:
        ref_path = REFERENCE_DIR / f"{stem}_{args.run_id}.json"
        got_path = args.results_dir / f"{stem}_{args.run_id}.json"
        try:
            ref = load_json(ref_path)["summary"]
            got = load_json(got_path)["summary"]
        except FileNotFoundError as exc:
            print(f"  [SKIP] {exc}")
            all_ok = False
            continue
        ok, lines = compare_summary(stem, ref, got, keys)
        all_ok = all_ok and ok
        print(f"\n{stem}:")
        print("\n".join(lines))

    if all_ok:
        print("\nAll metrics within tolerance.")
        return 0
    print("\nSome metrics differ. See EVAL_REPORT.md for expected numbers and tolerances.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
