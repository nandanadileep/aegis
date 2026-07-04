# LongMemEval-S benchmark harness

Evaluate Aegis memory retrieval and end-to-end QA against **[LongMemEval-S](https://arxiv.org/abs/2409.11965)** (~115k-token haystacks, 500 questions).

**Published results:** [`EVAL_REPORT.md`](EVAL_REPORT.md) (dev slice, n=10)  
**Reference JSON:** [`reference/`](reference/) (committed numbers to compare against)

---

## Quick start

```bash
cd aegis
pip install -r requirements.txt -r requirements-benchmark.txt

# 1. Services + keys (see Setup below)
cp .env.example .env   # if present; otherwise create .env

# 2. Dataset (~large JSON, gitignored)
python3 benchmarks/download_data.py

# 3. Smoke test (no LLM indexing cost)
python3 benchmarks/run_retrieval.py --backend flat_rag --limit 5

# 4. Dev slice (matches EVAL_REPORT numbers)
python3 benchmarks/run_retrieval.py --backend aegis --limit 10 --run-id dev --backfill-embeddings
python3 benchmarks/run_retrieval.py --backend flat_rag --limit 10 --run-id dev
python3 benchmarks/run_qa.py --backend aegis --limit 10 --run-id dev --backfill-embeddings
python3 benchmarks/run_qa.py --backend flat_rag --limit 10 --run-id dev

# 5. Compare to committed reference
python3 benchmarks/verify_reference.py --run-id dev
python3 benchmarks/compare_results.py --run-id dev
```

---

## Reproduce our numbers

These steps reproduce the **dev slice (n=10)** reported in [`EVAL_REPORT.md`](EVAL_REPORT.md).

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.10+** | Same as main app |
| **Neo4j 5.x** | Local or remote; benchmark graphs use isolated `person_id` values prefixed with `bench-lme-` |
| **Anthropic API key** | Ingest + QA reader/judge (`anthropic/claude-haiku-4-5`) |
| **~2 GB disk** | Dataset + local BGE model download on first run |

### Pinned configuration (dev run)

Add to `.env` (or export) for closest match to published numbers:

```bash
# Indexing (per session during ingest)
BENCH_LLM_MODEL=anthropic/claude-haiku-4-5

# QA reader + judge
BENCH_READER_MODEL=anthropic/claude-haiku-4-5
BENCH_JUDGE_MODEL=anthropic/claude-haiku-4-5
ANTHROPIC_API_KEY=...

# Embeddings (local BGE, free — default)
BENCH_ENABLE_EMBEDDINGS=1
BENCH_EMBEDDING_PROVIDER=local
BENCH_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

# Neo4j (inherits NEO4J_* from main app)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
```

### Commands (copy-paste)

```bash
cd aegis

python3 benchmarks/download_data.py

# Phase 1 — retrieval (reuse checkpoints on retry)
python3 benchmarks/run_retrieval.py --backend flat_rag --limit 10 --run-id dev
python3 benchmarks/run_retrieval.py --backend aegis --limit 10 --run-id dev --backfill-embeddings

# Phase 2 — end-to-end QA
python3 benchmarks/run_qa.py --backend flat_rag --limit 10 --run-id dev
python3 benchmarks/run_qa.py --backend aegis --limit 10 --run-id dev --backfill-embeddings

# Verify + compare
python3 benchmarks/verify_reference.py --run-id dev
python3 benchmarks/compare_results.py --run-id dev
```

### Expected summary metrics

| Run | recall@10 | ndcg@10 | qa_accuracy |
|-----|-----------|---------|-------------|
| flat_rag retrieval | **1.00** | **0.96** | — |
| aegis retrieval | **1.00** | **0.75** | — |
| flat_rag QA | 1.00 | — | **0.70** |
| aegis QA | 1.00 | — | **0.80** |

`verify_reference.py` checks your `benchmarks/results/*_dev.json` against [`reference/`](reference/) with tolerances (retrieval ±0.05–0.10; QA ±0.15 for LLM judge variance).

**Tips**

- **Skip re-ingest:** checkpoints live in `benchmarks/results/checkpoints/{backend}-dev/`. Delete a checkpoint file or pass `--force-reingest` to rebuild.
- **Embeddings only:** if graphs are already ingested without vectors, `--backfill-embeddings` embeds existing Neo4j nodes (no LLM re-extraction).
- **flat_rag first:** zero indexing cost — validates harness + dataset before spending on Aegis ingest.

---

## Setup

1. **Neo4j** running locally (or set `NEO4J_*` in `.env`). Benchmark graphs use isolated `person_id` values prefixed with `bench-lme-`.

2. **API keys** in `.env`:

```bash
# Extraction during indexing (per session)
BENCH_LLM_MODEL=groq/llama-3.3-70b-versatile   # or groq/llama-3.1-8b-instant (faster, weaker extraction)

# End-to-end QA reader + judge
BENCH_READER_MODEL=anthropic/claude-3-5-sonnet-latest
BENCH_JUDGE_MODEL=anthropic/claude-3-5-sonnet-latest
ANTHROPIC_API_KEY=...

# Embeddings are ON by default (local BGE, free). Disable with BENCH_ENABLE_EMBEDDINGS=0.
# To use OpenAI instead (needs credits):
# BENCH_EMBEDDING_PROVIDER=openai
# BENCH_EMBEDDING_MODEL=text-embedding-3-small
# EMBEDDING_DIMENSIONS=1536
```

3. **Download dataset** (~large JSON):

```bash
cd aegis
python3 benchmarks/download_data.py
```

---

## Directory layout

```
benchmarks/
  README.md              ← you are here
  EVAL_REPORT.md         ← published numbers (dev slice)
  reference/             ← committed JSON for verify_reference.py
  download_data.py       ← fetch LongMemEval-S cleaned JSON
  run_retrieval.py       ← Phase 1: Recall@k, NDCG@k
  run_qa.py              ← Phase 2: reader + judge accuracy
  compare_results.py     ← side-by-side retrieval table
  verify_reference.py    ← diff your run vs reference/
  config.py              ← env-driven defaults
  backends/
    aegis.py             ← ERF graph pipeline + retrieve_memory
    flat_rag.py          ← BM25-over-turns baseline
  data/                  ← gitignored (download_data.py)
  results/               ← gitignored (your local runs)
```

---

## Phase 1 — Retrieval metrics

Session-level **Recall@k** and **NDCG@k** vs `answer_session_ids` (skips 30 abstention questions).

```bash
# Smoke test: 5 questions, flat RAG baseline (no LLM indexing cost)
python3 benchmarks/run_retrieval.py --backend flat_rag --limit 5

# Aegis on 10 questions (streaming ingest = 1 LLM extraction per session)
python3 benchmarks/run_retrieval.py --backend aegis --limit 10

# Full run (expensive: ~500 instances × ~40 sessions × extraction LLM calls)
python3 benchmarks/run_retrieval.py --backend aegis --limit 0
```

Results: `benchmarks/results/retrieval_{backend}_{run_id}.json`

Checkpoints (skip re-ingest on retry): `benchmarks/results/checkpoints/`

### Flags

| Flag | Description |
|------|-------------|
| `--limit N` | First N questions (0 = all 500) |
| `--offset N` | Skip first N questions |
| `--run-id ID` | Suffix for output files (e.g. `dev`) |
| `--ks 5 10 20` | Recall/NDCG cutoffs |
| `--no-as-of` | Disable `as_of=question_date` for Aegis |
| `--force-reingest` | Ignore ingest checkpoints |
| `--backfill-embeddings` | Embed existing graph data (Aegis only) |

---

## Phase 2 — End-to-end QA

Retrieve → reader LLM → LLM judge vs gold answer.

```bash
python3 benchmarks/run_qa.py --backend aegis --limit 10
python3 benchmarks/run_qa.py --backend flat_rag --limit 10
```

Outputs:

- `benchmarks/results/qa_{backend}_{run_id}.json` — full run log
- `benchmarks/results/qa_{backend}_{run_id}.jsonl` — hypotheses (LongMemEval-compatible shape)

---

## Backends

| Backend | Indexing | Retrieval |
|---------|----------|-----------|
| `aegis` | `run_graph_pipeline` per session → Neo4j ERF | `retrieve_memory` + episode→session mapping |
| `flat_rag` | BM25 index over turns (in-memory) | Top turns → ranked sessions |

---

## Cost guidance

LongMemEval-S has ~40 sessions per instance. A full Aegis run is roughly:

`500 questions × ~40 sessions = ~20,000 extraction calls`

Use `--limit 10` for development. Flat RAG has **zero** indexing LLM cost — use it to validate the harness before scaling.

---

## Interpreting results

- **Recall@10** — did any gold evidence session appear in the top 10 retrieved sessions?
- **NDCG@10** — rank quality of retrieved sessions
- **qa_accuracy** — end-to-end answer correctness (reader + judge dependent)

Break down by `question_type` in the results JSON for temporal-reasoning vs knowledge-update gaps.

---

## Tests

```bash
cd aegis
python3 benchmarks/test_harness.py
```

Unit tests cover metrics, flat_rag backend, and Zep context formatting (no Neo4j or API keys required).
