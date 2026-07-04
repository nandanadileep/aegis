#!/usr/bin/env python3
"""Run LongMemEval-S end-to-end QA (retrieve + reader + judge)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from benchmarks.config import apply_benchmark_env
apply_benchmark_env()

from benchmarks.backends import AegisBackend, FlatRAGBackend
from benchmarks.config import (
    BENCH_JUDGE_MODEL,
    BENCH_QA_TOP_K,
    BENCH_READER_MODEL,
    CHECKPOINTS_DIR,
    DEFAULT_DATA_FILE,
    RESULTS_DIR,
)
from benchmarks.data_format import is_abstention, iter_sessions, load_longmemeval, parse_question_date
from benchmarks.llm import bench_completion, judge_answer
from benchmarks.metrics import aggregate_metrics, session_recall_at_k
from benchmarks.run_retrieval import build_backend, ingest_instance

READER_PROMPT = """You are a helpful assistant with access to retrieved memory.

Use ONLY the memory context below to answer the question. If the answer is not in the memory, say you do not know.

Memory context:
{memory_context}

Question (asked on {question_date}):
{question}

First extract relevant notes from the memory, then give a concise final answer."""


def answer_with_reader(
    question: str,
    question_date: str,
    memory_context: str,
    model: str,
) -> str:
    prompt = READER_PROMPT.format(
        memory_context=memory_context or "No memory retrieved.",
        question=question,
        question_date=question_date or "unknown",
    )
    return bench_completion(model, [{"role": "user", "content": prompt}], temperature=0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="LongMemEval-S QA benchmark")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--backend", choices=["aegis", "flat_rag", "session_summary"], default="aegis")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=BENCH_QA_TOP_K)
    parser.add_argument("--reader-model", default=BENCH_READER_MODEL)
    parser.add_argument("--judge-model", default=BENCH_JUDGE_MODEL)
    parser.add_argument("--run-id", type=str, default="")
    parser.add_argument("--force-reingest", action="store_true")
    parser.add_argument(
        "--backfill-embeddings",
        action="store_true",
        help="Embed existing graph data before QA (Aegis only)",
    )
    args = parser.parse_args()

    if not args.data.exists():
        print(f"Dataset not found: {args.data}")
        print("Run: python benchmarks/download_data.py")
        sys.exit(1)

    items = load_longmemeval(args.data)
    if args.offset:
        items = items[args.offset:]
    if args.limit:
        items = items[:args.limit]

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = CHECKPOINTS_DIR / f"{args.backend}-{run_id}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    backend = build_backend(args.backend, use_as_of=True)
    per_question = []
    hypothesis_lines = []

    for item in items:
        question_id = item["question_id"]
        question = str(item.get("question") or "")
        gold = str(item.get("answer") or "")

        checkpoint_path = checkpoint_dir / f"{question_id}.json"
        if args.force_reingest and checkpoint_path.exists():
            checkpoint_path.unlink()
        ingest_instance(backend, item, checkpoint_path)
        if args.backfill_embeddings and hasattr(backend, "backfill_instance_embeddings"):
            counts = backend.backfill_instance_embeddings(question_id)
            if any(counts.values()):
                print(f"[embed] {question_id} {counts}", flush=True)

        as_of = parse_question_date(item.get("question_date"))
        retrieval = backend.retrieve(question_id, question, as_of=as_of, top_k=args.top_k)
        hypothesis = answer_with_reader(
            question,
            str(item.get("question_date") or ""),
            retrieval.context_text,
            args.reader_model,
        )
        correct = judge_answer(question, gold, hypothesis, model=args.judge_model)

        row = {
            "question_id": question_id,
            "question_type": item.get("question_type"),
            "qa_correct": 1.0 if correct else 0.0,
            "recall@10": session_recall_at_k(
                retrieval.session_ids,
                list(item.get("answer_session_ids") or []),
                10,
            ) if not is_abstention(item) else None,
            "hypothesis": hypothesis,
            "gold": gold,
            "latency_ms": retrieval.latency_ms,
        }
        per_question.append(row)
        hypothesis_lines.append({"question_id": question_id, "hypothesis": hypothesis})
        print(
            f"[qa] {question_id} correct={correct} type={item.get('question_type')}",
            flush=True,
        )

    summary = aggregate_metrics(
        [r for r in per_question if r.get("recall@10") is not None],
        ks=[10],
    )
    summary["qa_accuracy"] = sum(r["qa_correct"] for r in per_question) / max(len(per_question), 1)
    summary["backend"] = args.backend
    summary["reader_model"] = args.reader_model
    summary["judge_model"] = args.judge_model
    summary["run_id"] = run_id

    out_path = RESULTS_DIR / f"qa_{args.backend}_{run_id}.json"
    out_path.write_text(json.dumps({"summary": summary, "questions": per_question}, indent=2))
    hyp_path = RESULTS_DIR / f"qa_{args.backend}_{run_id}.jsonl"
    hyp_path.write_text("\n".join(json.dumps(line) for line in hypothesis_lines) + "\n")

    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_path}")
    print(f"Wrote {hyp_path}")


if __name__ == "__main__":
    main()
