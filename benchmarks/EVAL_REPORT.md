# LongMemEval-S Evaluation Report

**Last updated:** 2026-07-04  
**Slice:** dev (`n=10`, first 10 non-abstention questions)  
**Dataset:** [LongMemEval-S cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) (`longmemeval_s_cleaned.json`)

> Published numbers and raw JSON live in [`benchmarks/reference/`](reference/).  
> To re-run locally, see [Reproduce our numbers](README.md#reproduce-our-numbers) in `benchmarks/README.md`.

---

## Executive summary

On a 10-question dev slice of LongMemEval-S, **Aegis graph memory matches flat BM25 RAG on session recall@10 (1.0)** but ranks the gold session lower on average (**NDCG@10: 0.75 vs 0.96**). Despite weaker session ranking, Aegis edges flat RAG on end-to-end QA accuracy (**80% vs 70%**) — though at n=10 that is a one-question margin and should be read as a directional signal, not a significant result. The robust, large gap is that **both fact-level (Aegis, 80%) and turn-level (flat_rag, 70%) memory far outperform the session-summary baseline (20%)**, which loses the specific detail during summarization.

**Takeaway:** graph memory is not worse at finding answers — it packages them better for downstream LLMs. A third baseline, **session-summary RAG**, trails both: condensed summaries frequently drop the specific fact, so the reader correctly abstains ("I don't know") and scores far lower.

| Phase | flat_rag | Aegis | session_summary | Winner |
|-------|----------|-------|-----------------|--------|
| Recall@10 | 1.00 | 1.00 | 0.80 | flat_rag / Aegis |
| NDCG@10 | **0.96** | 0.75 | 0.68 | flat_rag |
| QA accuracy | 0.70 | **0.80** | 0.20 | Aegis |
| Retrieval latency (avg) | ~30 ms | ~130–250 ms | ~30 ms* | flat_rag / session_summary |

\* session_summary retrieval latency is per-question after summaries are built; building the summaries themselves is a heavy one-time offline pass.

> **Judge correction (2026-07-04):** the automated LLM judge over-credited abstentions. On hand-review it scored four explicit "I do not know" answers as correct for the **session_summary** backend, inflating its QA accuracy from **0.60 → corrected 0.20**. The `flat_rag` (0.70) and `Aegis` (0.80) numbers were unaffected — every graded answer matched hand-review. Corrected per-question grades are committed as `qa_*_dev_corrected.json`.

---

## Setup

| Component | Configuration |
|-----------|---------------|
| **Aegis ingest** | ERF pipeline (`run_graph_pipeline`), `anthropic/claude-haiku-4-5`, episodic context n=4 |
| **Aegis retrieval** | Hybrid BM25 + local BGE (`BAAI/bge-small-en-v1.5`) + BFS + RRF, top-20 facts/entities, `as_of=question_date` |
| **flat_rag baseline** | In-memory BM25 over all turns (no extraction, no graph) |
| **QA reader / judge** | `anthropic/claude-haiku-4-5` |

Commands:

```bash
cd aegis

# Phase 1 — retrieval
python3 benchmarks/run_retrieval.py --backend aegis --limit 10 --run-id dev --backfill-embeddings
python3 benchmarks/run_retrieval.py --backend flat_rag --limit 10 --run-id dev

# Phase 2 — end-to-end QA
python3 benchmarks/run_qa.py --backend aegis --limit 10 --run-id dev --backfill-embeddings
python3 benchmarks/run_qa.py --backend flat_rag --limit 10 --run-id dev

# Side-by-side table
python3 benchmarks/compare_results.py --run-id dev
```

---

## Phase 1: Session-level retrieval

| Metric | flat_rag | Aegis | Notes |
|--------|----------|-------|-------|
| **Recall@5** | 1.00 | 0.90 | Aegis misses gold in top-5 once (`c5e8278d`, gold at rank 6) |
| **Recall@10** | 1.00 | 1.00 | Both find gold session within top 10 |
| **NDCG@10** | **0.96** | **0.75** | flat_rag ranks gold at **#1** on 8/10; Aegis at **#1** on 5/10 |
| **Latency** | ~30 ms | ~130–250 ms (10s cold start on Q1) | Graph + hybrid search vs in-memory BM25 |

### Gold session rank (why NDCG differs)

| Question | flat_rag rank | Aegis rank |
|----------|---------------|------------|
| e47becba | 2 | 2 |
| 118b2229 | **1** | 4 |
| 51a45a95 | **1** | 2 |
| 58bf7951 | **1** | **1** |
| 1e043500 | **1** | **1** |
| c5e8278d | **1** | 6 |
| 6ade9755 | **1** | **1** |
| 6f9b354f | **1** | **1** |
| 58ef2f1c | **1** | 4 |
| f8c5f88b | **1** | **1** |

**Interpretation:** flat_rag scores individual *turns* by keyword overlap, so the answer turn often floats to rank 1. Aegis scores *facts* and maps back to sessions — the gold session is usually retrieved but at ranks 2–6 when other sessions produced lexically similar facts.

---

## Phase 2: End-to-end QA (retrieve → reader → judge)

QA accuracy below is **hand-corrected** (strict grading: an explicit "I do not know" counts as wrong). Raw judge output is preserved in `qa_*_dev.json`; corrected grades in `qa_*_dev_corrected.json`.

| Metric | flat_rag | Aegis | session_summary |
|--------|----------|-------|-----------------|
| **QA accuracy (corrected)** | 70% (7/10) | **80% (8/10)** | 20% (2/10) |
| **QA accuracy (raw judge)** | 70% | 80% | 60% |
| **Session recall@10** | 1.00 | 1.00 | 0.80 |

### Per-question results

Legend: ✓ correct · ✗ wrong · ✗! judge scored correct but answer was an explicit "I don't know" (corrected to wrong).

| Question | flat_rag QA | Aegis QA | session_summary QA | Notes |
|----------|-------------|----------|--------------------|-------|
| e47becba | ✓ | ✓ | ✓ | All three answer |
| 118b2229 | ✓ | ✓ | ✗! | summary abstains ("don't know commute") |
| 51a45a95 | ✗ | ✗ | ✗ | All fail |
| 58bf7951 | ✗ | ✓ | ✗! | **Aegis wins**; summary abstains ("don't know play") |
| 1e043500 | ✓ | ✓ | ✗! | summary abstains ("don't know playlist") |
| c5e8278d | ✓ | ✓ | ✗ | summary has new name, not the old one |
| 6ade9755 | ✓ | ✓ | ✗ | summary lacks studio name |
| 6f9b354f | ✓ | ✓ | ✓ | All three answer |
| 58ef2f1c | ✗ | ✗ | ✗ | All fail |
| f8c5f88b | ✓ | ✓ | ✗! | summary abstains ("don't know store") |

---

## Claims you can make (honest)

1. **Parity on recall:** Aegis graph memory finds the correct source session as often as flat BM25 RAG at recall@10 on this slice.
2. **Ranking gap:** flat_rag ranks the gold session higher (NDCG@10 0.96 vs 0.75) because turn-level BM25 is optimized for lexical match; fact-level retrieval dilutes session ordering.
3. **QA upside:** Despite lower NDCG, Aegis achieves **higher end-to-end QA accuracy** on this slice — structured `<FACTS>` / `<ENTITIES>` context helps the reader when gold isn't rank 1.
4. **Summaries lose facts:** session-summary RAG (20% corrected) trails both turn-level and graph memory because condensed summaries frequently drop the specific detail the question asks for.
5. **Temporal eval works:** `as_of=question_date` bi-temporal filtering is enabled (not `--no-as-of`).
6. **Zep-aligned pipeline:** Hybrid search + entity retrieval + Zep context format + local embeddings.

## Claims to avoid (until scaled up)

- Beating Zep/MemGPT on full LongMemEval-S (500 questions) — only n=10 dev slice run so far.
- Beating flat_rag on NDCG without further ranking tuning (cross-encoder rerank, session-level boost from `source_episode_id`).
- Treating **Aegis 80% vs flat_rag 70%** as significant — it is a one-question margin at n=10. The larger, more defensible gap is graph/turn-level memory vs the session-summary baseline (80%/70% vs 20%).
- Trusting the automated LLM judge unaudited — it over-credits abstentions (see judge-correction note above). Use `qa_*_dev_corrected.json` for reported numbers.
- Production latency at scale — dev slice only.

---

## Roadmap (full paper-grade eval)

1. **Scale to 50–100 questions** (or full 500):  
   `python3 benchmarks/run_retrieval.py --backend aegis --limit 100 --run-id paper-v1 --backfill-embeddings`
2. **Improve ranking:** episode-mentions reranker, boost facts from high-scoring sessions, or cross-encoder rerank.
3. **Full QA run** on the same slice with a fixed judge for reproducibility.
4. **Ablation:** `--no-as-of`, no embeddings, no communities — to show which components matter.
5. **Cost/latency table:** ingest LLM cost per session vs flat_rag (zero).

---

## Artifacts

| File | Description |
|------|-------------|
| [`reference/retrieval_aegis_dev.json`](reference/retrieval_aegis_dev.json) | Aegis retrieval run (committed) |
| [`reference/retrieval_flat_rag_dev.json`](reference/retrieval_flat_rag_dev.json) | flat_rag retrieval run (committed) |
| [`reference/qa_aegis_dev.json`](reference/qa_aegis_dev.json) | Aegis QA run (committed) |
| [`reference/qa_flat_rag_dev.json`](reference/qa_flat_rag_dev.json) | flat_rag QA run (committed) |
| `results/qa_aegis_dev_corrected.json` | Aegis QA, hand-corrected grades (80%) |
| `results/qa_flat_rag_dev_corrected.json` | flat_rag QA, hand-corrected grades (70%) |
| `results/qa_session_summary_dev_corrected.json` | session_summary QA, hand-corrected grades (60% → 20%) |

Local re-runs write to `benchmarks/results/` (gitignored). Checkpoints: `benchmarks/results/checkpoints/{backend}-dev/`.
