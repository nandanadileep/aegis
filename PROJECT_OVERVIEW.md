Aegis — Project Overview
========================

Aegis is a personalized AI memory layer. It listens to conversations,
extracts what matters, and stores it in a private, per-user knowledge graph.
Later, when the user chats again, Aegis retrieves the relevant memories so
the AI can respond like an old friend.

This document is the **technical map** for contributors and integrators.
For running the product locally, see [README.md](README.md).
For benchmark numbers and reproduction steps, see [benchmarks/EVAL_REPORT.md](benchmarks/EVAL_REPORT.md).


Documentation index
-------------------

| Doc | Audience | Contents |
|-----|----------|----------|
| [README.md](README.md) | Users | Run the app, stack, env vars |
| **PROJECT_OVERVIEW.md** (this file) | Contributors | Architecture, memory pipeline, components |
| [benchmarks/README.md](benchmarks/README.md) | Evaluators | LongMemEval-S harness, flags, cost guidance |
| [benchmarks/EVAL_REPORT.md](benchmarks/EVAL_REPORT.md) | Researchers / investors | Published dev-slice numbers |
| [benchmarks/WHITEPAPER.md](benchmarks/WHITEPAPER.md) | Investors / architects | When graph memory is worth the cost |
| [benchmarks/reference/](benchmarks/reference/) | Reproducers | Committed JSON to verify against |


What it is made of
------------------

```
aegis/
  app.py                      Flask API (chat, wallet, onboarding)
  mcp_server.py               MCP server for external agents
  scripts/
    graph_memory.py           Core ERF engine (Neo4j)
    user_summary.py           Natural-language user summary
    crypto.py                 Per-user encryption
    visualize_erf_graph.py      HTML graph viewer
    demo_graph_memory.py      Pipeline smoke test
    chat_with_memory.py       CLI chat with memory
  benchmarks/                 LongMemEval-S eval harness
  frontend/                   React + Vite UI
```

**External services**

- **Neo4j** — Entity-Relation-Fact graph, communities, vector + full-text indexes
- **Redis** — conversation history, cached summaries
- **LiteLLM** — Groq, Anthropic, OpenAI, etc.


Key features
------------

1. **Entity extraction** — people, places, organizations, skills, projects, goals, technologies, and other concepts from each message.

2. **Fact extraction** — links entities with temporal facts, e.g. `(Nandana)-[USES]->(Neo4j)` with text `"Nandana uses Neo4j for the AI memory app."`

3. **Entity resolution** — merges duplicate entities when the same thing is mentioned with slightly different names.

4. **Temporal awareness** — every fact gets a valid time window (`valid_from` / `valid_to`):
   - "started two weeks ago" → `valid_from` = two weeks ago
   - "used to work at Google" → `valid_to` = now
   - "no longer drinks coffee" → negation handling
   - Untimed facts are valid from the moment they are recorded.

5. **Bi-temporal provenance** — `created_at`, `source_episode_id`, optional `ingested_at`; supports **as-of retrieval** (filter facts valid at a given datetime).

6. **Contradiction detection** — fast rules (negation words) + LLM fallback; expired facts get `valid_to` set.

7. **Retrieval** (vector + BM25 + BFS + reranker):
   - scores facts by embedding similarity and token overlap,
   - walks the graph outward from top entities (BFS),
   - community-aware coarse retrieval before fact-level search,
   - merges and reranks (RRF default; MMR or cross-encoder optional).

8. **Community detection** — incremental re-clustering after writes; each community gets name, summary, and top facts.

9. **User summary** — top facts condensed into a paragraph, cached in Redis.

10. **Wallet / profile export** — `/api/wallet` returns a self-contained HTML memory profile.

11. **MCP server** — `get_memory(person_id, query)` and `add_memory(transcript, person_id)`.

12. **Structured ingestion** — `/api/memory/add` for JSON facts/entities (not only chat extraction).

13. **Per-user encryption** — facts, entity names, summaries, and community text encrypted per `person_id`.


Typical flow
------------

```
User sends a message
        |
        v
Extract entities and facts (with episodic context from recent turns)
        |
        v
Resolve duplicates, detect contradictions, mark old facts expired
        |
        v
Store entities and facts in Neo4j with temporal + provenance fields
        |
        v
Incremental community update and summarize
        |
        v
On reply: retrieve relevant memories (optionally as-of a datetime) → build context
```


Evaluation
----------

Aegis is evaluated on **[LongMemEval-S](https://arxiv.org/abs/2409.11965)** via `benchmarks/`.

**Dev slice (n=10) headline results** — full tables in [benchmarks/EVAL_REPORT.md](benchmarks/EVAL_REPORT.md):

| Metric | flat_rag | Aegis | session_summary |
|--------|----------|-------|-----------------|
| Recall@10 | 1.00 | 1.00 | 0.80 |
| NDCG@10 | 0.96 | 0.75 | 0.68 |
| QA accuracy | 0.70 | **0.80** | 0.20 |

QA accuracy is hand-corrected (strict grading; an explicit "I don't know" counts as wrong). The automated judge over-credited abstentions and inflated the session-summary score from 0.60 → 0.20; `flat_rag` and `Aegis` were unaffected. At n=10 the Aegis-vs-flat_rag gap is a one-question margin (directional only); the large, robust gap is fact-level/turn-level memory vs the session-summary baseline. See [EVAL_REPORT.md](benchmarks/EVAL_REPORT.md) for the judge-correction note and per-question grades.

**Reproduce locally** (Neo4j + Anthropic key required):

```bash
cd aegis
pip install -r requirements.txt -r requirements-benchmark.txt
python3 benchmarks/download_data.py
python3 benchmarks/run_retrieval.py --backend aegis --limit 10 --run-id dev --backfill-embeddings
python3 benchmarks/verify_reference.py --run-id dev
```

See [benchmarks/README.md](benchmarks/README.md) for the full harness, flags, and cost guidance.


Environment variables
---------------------

| Variable | Purpose |
|----------|---------|
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | Graph storage |
| `REDIS_URL` | Conversation history + summary cache |
| `LLM_MODEL`, `LLM_FAST`, `LLM_FALLBACK_LIST` | Chat + extraction models |
| `EMBEDDING_MODEL` | Optional; enables vector retrieval |
| `DAILY_MSG_LIMIT` | Rate limit per user |
| `GROQ_API_KEY` / `ANTHROPIC_API_KEY` | LLM providers (via LiteLLM) |
| `SUPABASE_URL`, `SUPABASE_JWT_SECRET` | Auth (product only) |

Benchmark-specific vars (`BENCH_*`) are documented in [benchmarks/README.md](benchmarks/README.md).


Notes
-----

- Embeddings are optional for the product; the benchmark harness enables local BGE by default.
- Community summarization uses one batched LLM call per pipeline run to keep latency reasonable.
- Cross-encoder reranking is optional; RRF works with no extra dependencies.
- Benchmark graphs use isolated `bench-lme-*` person IDs and do not touch production user data.
