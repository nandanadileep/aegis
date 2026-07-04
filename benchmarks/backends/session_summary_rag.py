"""Session-summary RAG baseline (Zep DMR / LongMemEval-style).

One LLM summary per session at ingest; retrieve with BM25 (+ optional vectors) over summaries.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.backends.base import RetrieveResult
from benchmarks.config import BENCH_ENABLE_EMBEDDINGS, BENCH_LLM_MODEL, BENCH_MAX_TRANSCRIPT_CHARS
from benchmarks.data_format import session_transcript, truncate_session_transcript
from benchmarks.llm import bench_llm_fn
from scripts.embeddings import make_embed_fn


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SessionSummaryRAGBackend:
    """Summarize each session, then hybrid-retrieve over session-level documents."""

    name = "session_summary"

    def __init__(self, llm_model: Optional[str] = None):
        self.llm_model = llm_model or BENCH_LLM_MODEL
        self.llm_fn = bench_llm_fn(self.llm_model)
        self.embed_fn = make_embed_fn() if BENCH_ENABLE_EMBEDDINGS else None
        self._summaries: Dict[str, Dict[str, str]] = {}
        self._embeddings: Dict[str, Dict[str, List[float]]] = {}

    def reset(self, instance_id: str) -> None:
        self._summaries.pop(instance_id, None)
        self._embeddings.pop(instance_id, None)

    def checkpoint_payload(self) -> Dict[str, Any]:
        return {
            "summaries": self._summaries,
            "embeddings": self._embeddings if BENCH_ENABLE_EMBEDDINGS else {},
        }

    def restore_checkpoint_payload(self, data: Dict[str, Any]) -> None:
        self._summaries = data.get("summaries") or {}
        self._embeddings = data.get("embeddings") or {}

    def has_instance(self, instance_id: str) -> bool:
        return bool(self._summaries.get(instance_id))

    def progress_payload(self, instance_id: str) -> Dict[str, Any]:
        return {"summaries": dict(self._summaries.get(instance_id, {}))}

    def restore_progress(self, instance_id: str, prog: Dict[str, Any]) -> None:
        summaries = prog.get("summaries") or {}
        if not summaries:
            return
        self._summaries[instance_id] = dict(summaries)
        if not self.embed_fn:
            return
        for session_id, text in summaries.items():
            embs = self.embed_fn([text])
            if embs:
                self._embeddings.setdefault(instance_id, {})[session_id] = embs[0]

    def _summarize_session(self, turns: List[Dict[str, Any]]) -> str:
        if any(str(t.get("role", "")).lower() == "user" for t in turns):
            transcript = truncate_session_transcript(turns, BENCH_MAX_TRANSCRIPT_CHARS)
        else:
            transcript = session_transcript(turns)
        if not transcript.strip():
            return ""
        prompt = (
            "Summarize this chat session in 3–6 sentences. "
            "Preserve concrete facts (names, dates, places, preferences) the user stated.\n\n"
            f"Session:\n{transcript}"
        )
        resp = self.llm_fn(messages=[{"role": "user", "content": prompt}], temperature=0.0)
        return (resp.choices[0].message.content or "").strip()

    def insert_session(
        self,
        instance_id: str,
        session_id: str,
        turns: List[Dict[str, Any]],
        session_date: Optional[str] = None,
        prior_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        summary = self._summarize_session(turns)
        if not summary:
            return
        self._summaries.setdefault(instance_id, {})[session_id] = summary
        if self.embed_fn:
            embs = self.embed_fn([summary])
            if embs:
                self._embeddings.setdefault(instance_id, {})[session_id] = embs[0]

    def _score_sessions(
        self,
        instance_id: str,
        query: str,
    ) -> List[Tuple[float, str, str]]:
        summaries = self._summaries.get(instance_id, {})
        if not summaries:
            return []

        query_tokens = set(_tokenize(query))
        query_emb: Optional[List[float]] = None
        if self.embed_fn:
            embs = self.embed_fn([query])
            query_emb = embs[0] if embs else None

        texts = list(summaries.values())
        session_ids = list(summaries.keys())
        doc_tokens = [_tokenize(t) for t in texts]
        avgdl = sum(len(t) for t in doc_tokens) / max(len(doc_tokens), 1)
        n_docs = len(texts)
        df: Counter[str] = Counter()
        for tokens in doc_tokens:
            df.update(set(tokens))

        k1, b = 1.5, 0.75
        scored: List[Tuple[float, str, str]] = []
        for session_id, text, tokens in zip(session_ids, texts, doc_tokens):
            tf = Counter(tokens)
            dl = len(tokens)
            bm25 = 0.0
            for term in query_tokens:
                if term not in df:
                    continue
                idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
                freq = tf.get(term, 0)
                denom = freq + k1 * (1 - b + b * dl / avgdl)
                bm25 += idf * (freq * (k1 + 1)) / (denom or 1.0)

            overlap = len(query_tokens & set(tokens)) / max(len(query_tokens), 1)
            bm25_norm = bm25 / (bm25 + 1.0) if bm25 > 0 else 0.0

            vec = 0.0
            if query_emb and session_id in self._embeddings.get(instance_id, {}):
                vec = _cosine_similarity(query_emb, self._embeddings[instance_id][session_id])

            if self.embed_fn and vec > 0:
                score = 0.6 * vec + 0.4 * max(bm25_norm, overlap)
            else:
                score = max(bm25_norm, overlap)

            if score > 0:
                scored.append((score, session_id, text))

        scored.sort(key=lambda row: row[0], reverse=True)
        return scored

    def retrieve(
        self,
        instance_id: str,
        query: str,
        as_of: Optional[datetime] = None,
        top_k: int = 20,
    ) -> RetrieveResult:
        started = time.perf_counter()
        scored = self._score_sessions(instance_id, query)

        ranked_session_ids: List[str] = []
        context_lines: List[str] = []
        for score, session_id, text in scored[:top_k]:
            ranked_session_ids.append(session_id)
            context_lines.append(f"[{session_id}] {text}")

        latency_ms = (time.perf_counter() - started) * 1000.0
        context_text = "\n".join(f"- {line}" for line in context_lines)
        return RetrieveResult(
            session_ids=ranked_session_ids,
            context_text=context_text or "No relevant session summaries.",
            latency_ms=latency_ms,
            metadata={"summary_hits": len(context_lines)},
        )
