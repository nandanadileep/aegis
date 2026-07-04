"""Aegis ERF graph memory backend for LongMemEval."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from benchmarks.config import (
    BENCH_ENABLE_EMBEDDINGS,
    BENCH_ENTITY_TOP_K,
    BENCH_EPISODIC_TURNS,
    BENCH_LLM_MODEL,
    BENCH_MAX_TRANSCRIPT_CHARS,
    BENCH_NEO4J_DATABASE,
    BENCH_RERANK_METHOD,
)
from benchmarks.data_format import (
    parse_question_date,
    session_transcript,
    truncate_session_transcript,
)
from benchmarks.llm import bench_llm_fn
from benchmarks.neo4j_util import bench_person_id, get_driver, wipe_person

from scripts.embeddings import make_embed_fn
from scripts.graph_memory import (
    backfill_embeddings,
    create_episode,
    ensure_indexes,
    format_zep_context,
    format_episodic_context,
    retrieve_memory,
    run_graph_pipeline,
)


class AegisBackend:
    name = "aegis"

    def __init__(
        self,
        database: Optional[str] = None,
        llm_model: Optional[str] = None,
        use_as_of: bool = True,
        skip_communities: bool = False,
    ):
        self.database = database or BENCH_NEO4J_DATABASE
        self.llm_model = llm_model or BENCH_LLM_MODEL
        self.use_as_of = use_as_of
        self.skip_communities = skip_communities
        self.driver = get_driver()
        self.embed_fn = make_embed_fn() if BENCH_ENABLE_EMBEDDINGS else None
        ensure_indexes(self.driver, self.database)

        self._history: Dict[str, List[Dict[str, str]]] = {}

    def backfill_instance_embeddings(self, instance_id: str) -> Dict[str, int]:
        """Embed existing graph nodes/facts that were ingested without vectors."""
        if not self.embed_fn:
            return {"entities": 0, "facts": 0, "communities": 0}
        return backfill_embeddings(
            self.driver,
            self.database,
            bench_person_id(instance_id),
            embed_fn=self.embed_fn,
        )

    def reset(self, instance_id: str) -> None:
        person_id = bench_person_id(instance_id)
        wipe_person(self.driver, self.database, person_id)
        self._history.pop(instance_id, None)

    def insert_session(
        self,
        instance_id: str,
        session_id: str,
        turns: List[Dict[str, Any]],
        session_date: Optional[str] = None,
        prior_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        person_id = bench_person_id(instance_id)
        if session_id.startswith("answer_"):
            transcript = session_transcript(turns)
        else:
            transcript = truncate_session_transcript(turns, BENCH_MAX_TRANSCRIPT_CHARS)
        if not transcript.strip():
            return

        history = self._history.setdefault(instance_id, [])
        if prior_turns is not None:
            episodic_messages = [
                {"role": str(t.get("role", "user")), "content": str(t.get("content", ""))}
                for t in prior_turns
            ]
        else:
            episodic_messages = list(history)

        previous_messages = format_episodic_context(
            episodic_messages,
            max_turns=BENCH_EPISODIC_TURNS,
        )

        ref_time = parse_question_date(session_date)

        episode_id = create_episode(
            self.driver,
            self.database,
            person_id,
            body=transcript,
            source="longmemeval",
            episode_id=session_id,
        )
        llm_fn = bench_llm_fn(self.llm_model)
        run_graph_pipeline(
            conversation=transcript,
            person_id=person_id,
            driver=self.driver,
            database=self.database,
            ref_time=ref_time,
            episode_id=episode_id,
            previous_messages=previous_messages,
            llm_fn=llm_fn,
            embed_fn=self.embed_fn,
        )

        for turn in turns:
            history.append({
                "role": str(turn.get("role", "user")),
                "content": str(turn.get("content", "")),
            })

    def retrieve(
        self,
        instance_id: str,
        query: str,
        as_of: Optional[datetime] = None,
        top_k: int = 20,
    ) -> "RetrieveResult":
        from benchmarks.backends.base import RetrieveResult

        person_id = bench_person_id(instance_id)
        started = time.perf_counter()
        memory = retrieve_memory(
            self.driver,
            self.database,
            person_id,
            query,
            fact_top_k=top_k,
            entity_top_k=BENCH_ENTITY_TOP_K,
            embed_fn=self.embed_fn,
            as_of=as_of if self.use_as_of else None,
            rerank_method=BENCH_RERANK_METHOD,
        )
        facts = memory["facts"]
        latency_ms = (time.perf_counter() - started) * 1000.0

        ranked_session_ids: List[str] = []
        seen = set()
        for fact in facts:
            episode_id = fact.get("source_episode_id")
            if episode_id and episode_id not in seen:
                seen.add(episode_id)
                ranked_session_ids.append(episode_id)

        context_text = format_zep_context(facts, memory.get("entities") or [])
        return RetrieveResult(
            session_ids=ranked_session_ids,
            context_text=context_text,
            latency_ms=latency_ms,
            metadata={
                "fact_count": len(facts),
                "entity_count": len(memory.get("entities") or []),
                "context_chars": len(context_text),
            },
        )
