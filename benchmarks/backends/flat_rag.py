"""In-memory flat RAG baseline (BM25 over turns)."""
from __future__ import annotations

import math
import re
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.backends.base import RetrieveResult


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class FlatRAGBackend:
    name = "flat_rag"

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: Dict[str, List[Tuple[str, int, str]]] = {}

    def reset(self, instance_id: str) -> None:
        self._docs.pop(instance_id, None)

    def insert_session(
        self,
        instance_id: str,
        session_id: str,
        turns: List[Dict[str, Any]],
        session_date: Optional[str] = None,
        prior_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        docs = self._docs.setdefault(instance_id, [])
        for turn_idx, turn in enumerate(turns):
            role = str(turn.get("role", "user"))
            content = str(turn.get("content", "")).strip()
            if not content:
                continue
            docs.append((session_id, turn_idx, f"{role}: {content}"))

    def _bm25_scores(self, instance_id: str, query: str) -> List[Tuple[float, str, int, str]]:
        docs = self._docs.get(instance_id, [])
        if not docs:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        doc_tokens = [_tokenize(text) for _, _, text in docs]
        avgdl = sum(len(tokens) for tokens in doc_tokens) / max(len(doc_tokens), 1)
        df: Counter[str] = Counter()
        for tokens in doc_tokens:
            df.update(set(tokens))

        n_docs = len(docs)
        scored: List[Tuple[float, str, int, str]] = []
        for (session_id, turn_idx, text), tokens in zip(docs, doc_tokens):
            tf = Counter(tokens)
            dl = len(tokens)
            score = 0.0
            for term in query_tokens:
                if term not in df:
                    continue
                idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
                freq = tf.get(term, 0)
                denom = freq + self.k1 * (1 - self.b + self.b * dl / avgdl)
                score += idf * (freq * (self.k1 + 1)) / (denom or 1.0)
            scored.append((score, session_id, turn_idx, text))
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
        scored = self._bm25_scores(instance_id, query)

        ranked_session_ids: List[str] = []
        seen_sessions = set()
        context_lines: List[str] = []
        for score, session_id, turn_idx, text in scored:
            if len(context_lines) >= top_k:
                break
            if score <= 0:
                continue
            context_lines.append(text)
            if session_id not in seen_sessions:
                seen_sessions.add(session_id)
                ranked_session_ids.append(session_id)

        latency_ms = (time.perf_counter() - started) * 1000.0
        context_text = "\n".join(f"- {line}" for line in context_lines)
        return RetrieveResult(
            session_ids=ranked_session_ids,
            context_text=context_text,
            latency_ms=latency_ms,
            metadata={"turn_hits": len(context_lines)},
        )
