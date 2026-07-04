#!/usr/bin/env python3
"""Run LongMemEval-S session-level retrieval evaluation."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from benchmarks.backends import (
    AegisBackend,
    FlatRAGBackend,
    MemoryBackend,
    SessionSummaryRAGBackend,
)
from benchmarks.config import (
    BENCH_INGEST_DELAY_S,
    BENCH_RETRIEVAL_TOP_K,
    CHECKPOINTS_DIR,
    DEFAULT_DATA_FILE,
    RESULTS_DIR,
    apply_benchmark_env,
)
from benchmarks.data_format import is_abstention, iter_sessions, load_longmemeval, parse_question_date
from benchmarks.metrics import aggregate_metrics, session_ndcg_at_k, session_recall_at_k


BACKEND_CHOICES = ["aegis", "flat_rag", "session_summary"]


def build_backend(name: str, use_as_of: bool) -> MemoryBackend:
    if name == "aegis":
        return AegisBackend(use_as_of=use_as_of)
    if name == "flat_rag":
        return FlatRAGBackend()
    if name == "session_summary":
        return SessionSummaryRAGBackend()
    raise ValueError(f"Unknown backend: {name}")


def _restore_checkpoint(backend: MemoryBackend, checkpoint_path: Path) -> None:
    if not checkpoint_path.exists():
        return
    restore = getattr(backend, "restore_checkpoint_payload", None)
    if not callable(restore):
        return
    try:
        restore(json.loads(checkpoint_path.read_text()))
    except Exception:
        pass


def _instance_ready(backend: MemoryBackend, instance_id: str, checkpoint_path: Path) -> bool:
    """True when this instance can skip ingest (checkpoint + in-memory state)."""
    if not checkpoint_path.exists():
        return False
    backend_name = getattr(backend, "name", None)
    if backend_name == "flat_rag":
        docs = getattr(backend, "_docs", {})
        return bool(docs.get(instance_id))
    if backend_name == "session_summary":
        has_instance = getattr(backend, "has_instance", None)
        return bool(has_instance(instance_id)) if callable(has_instance) else False
    return True


def ingest_instance(
    backend: MemoryBackend,
    item: dict,
    checkpoint_path: Path,
    ingest_delay_s: float = 0.0,
) -> None:
    instance_id = item["question_id"]
    _restore_checkpoint(backend, checkpoint_path)
    if _instance_ready(backend, instance_id, checkpoint_path):
        return

    progress_path = checkpoint_path.with_suffix(".progress.json")
    completed_sessions: List[str] = []
    if progress_path.exists():
        try:
            prog = json.loads(progress_path.read_text())
            completed_sessions = prog.get("sessions", [])
            restore_progress = getattr(backend, "restore_progress", None)
            if callable(restore_progress):
                restore_progress(instance_id, prog)
        except Exception:
            completed_sessions = []
    else:
        backend.reset(instance_id)

    history_turns: List[dict] = []
    for session_id, turns, session_date in iter_sessions(item):
        if session_id in completed_sessions:
            history_turns.extend(turns)
            continue
        backend.insert_session(
            instance_id,
            session_id,
            turns,
            session_date=session_date,
            prior_turns=history_turns,
        )
        history_turns.extend(turns)
        completed_sessions.append(session_id)
        prog_data = {
            "sessions": completed_sessions,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        progress_payload = getattr(backend, "progress_payload", None)
        if callable(progress_payload):
            prog_data.update(progress_payload(instance_id))
        progress_path.write_text(json.dumps(prog_data))
        if ingest_delay_s > 0:
            time.sleep(ingest_delay_s)

    payload = {"ingested_at": datetime.now(timezone.utc).isoformat()}
    checkpoint_payload = getattr(backend, "checkpoint_payload", None)
    if callable(checkpoint_payload):
        payload.update(checkpoint_payload())
    checkpoint_path.write_text(json.dumps(payload))
    if progress_path.exists():
        progress_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="LongMemEval-S retrieval benchmark")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="aegis")
    parser.add_argument("--limit", type=int, default=0, help="Max questions (0 = all)")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--ks", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--top-k", type=int, default=BENCH_RETRIEVAL_TOP_K)
    parser.add_argument("--no-as-of", action="store_true", help="Disable bi-temporal as_of for Aegis")
    parser.add_argument("--run-id", type=str, default="")
    parser.add_argument("--force-reingest", action="store_true")
    parser.add_argument(
        "--backfill-embeddings",
        action="store_true",
        help="Embed existing graph data (no LLM re-extraction)",
    )
    parser.add_argument(
        "--ingest-delay",
        type=float,
        default=BENCH_INGEST_DELAY_S,
        help="Seconds to pause between session ingests (Groq TPM)",
    )
    args = parser.parse_args()
    apply_benchmark_env()

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
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = CHECKPOINTS_DIR / f"{args.backend}-{run_id}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    backend = build_backend(args.backend, use_as_of=not args.no_as_of)
    per_question = []
    started = time.perf_counter()

    for item in items:
        question_id = item["question_id"]
        if is_abstention(item):
            continue

        checkpoint_path = checkpoint_dir / f"{question_id}.json"
        progress_path = checkpoint_path.with_suffix(".progress.json")
        if args.force_reingest:
            for path in (checkpoint_path, progress_path):
                if path.exists():
                    path.unlink()

        print(f"[ingest] {question_id}", flush=True)
        ingest_instance(
            backend,
            item,
            checkpoint_path,
            ingest_delay_s=args.ingest_delay
            if args.backend in ("aegis", "session_summary")
            else 0.0,
        )
        if args.backfill_embeddings and hasattr(backend, "backfill_instance_embeddings"):
            counts = backend.backfill_instance_embeddings(question_id)
            print(f"[embed] {question_id} {counts}", flush=True)

        as_of = parse_question_date(item.get("question_date"))
        retrieval = backend.retrieve(
            question_id,
            str(item.get("question") or ""),
            as_of=as_of,
            top_k=args.top_k,
        )
        gold_sessions = list(item.get("answer_session_ids") or [])
        row = {
            "question_id": question_id,
            "question_type": item.get("question_type"),
            "latency_ms": retrieval.latency_ms,
            "retrieved_session_ids": retrieval.session_ids,
            "gold_session_ids": gold_sessions,
            "metadata": retrieval.metadata,
        }
        for k in args.ks:
            row[f"recall@{k}"] = session_recall_at_k(retrieval.session_ids, gold_sessions, k)
            row[f"ndcg@{k}"] = session_ndcg_at_k(retrieval.session_ids, gold_sessions, k)
        per_question.append(row)
        print(
            f"[retrieve] {question_id} recall@10={row.get('recall@10', 0):.3f} "
            f"latency={retrieval.latency_ms:.0f}ms",
            flush=True,
        )

    summary = aggregate_metrics(per_question, args.ks)
    summary["backend"] = args.backend
    summary["run_id"] = run_id
    summary["elapsed_s"] = time.perf_counter() - started

    out = {
        "summary": summary,
        "questions": per_question,
    }
    out_path = RESULTS_DIR / f"retrieval_{args.backend}_{run_id}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
