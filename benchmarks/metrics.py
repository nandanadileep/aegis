"""Retrieval and QA metrics for LongMemEval."""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence, Set


def session_recall_at_k(
    retrieved_session_ids: Sequence[str],
    gold_session_ids: Sequence[str],
    k: int,
) -> float:
    if not gold_session_ids:
        return 0.0
    top_k = set(retrieved_session_ids[:k])
    return 1.0 if any(sid in top_k for sid in gold_session_ids) else 0.0


def session_ndcg_at_k(
    retrieved_session_ids: Sequence[str],
    gold_session_ids: Sequence[str],
    k: int,
) -> float:
    gold: Set[str] = set(gold_session_ids)
    if not gold:
        return 0.0
    dcg = 0.0
    for rank, sid in enumerate(retrieved_session_ids[:k], start=1):
        if sid in gold:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def aggregate_metrics(rows: Iterable[Dict[str, float]], ks: Sequence[int]) -> Dict[str, float]:
    rows = list(rows)
    if not rows:
        return {}
    out: Dict[str, float] = {"count": float(len(rows))}
    for k in ks:
        recall_key = f"recall@{k}"
        ndcg_key = f"ndcg@{k}"
        out[recall_key] = sum(r.get(recall_key, 0.0) for r in rows) / len(rows)
        out[ndcg_key] = sum(r.get(ndcg_key, 0.0) for r in rows) / len(rows)
    if rows and "qa_correct" in rows[0]:
        out["qa_accuracy"] = sum(r.get("qa_correct", 0.0) for r in rows) / len(rows)
    return out
