# Benchmark baselines

What to compare Aegis against for a **credible** technical article or paper.

## Tier 1 — Implement in this harness (apples-to-apples)

| Backend | What it is | Used by | Status |
|---------|------------|---------|--------|
| `flat_rag` | BM25 over **turns** | Minimal RAG floor | ✅ |
| `session_summary` | LLM **one summary per session** → BM25 (+ BGE hybrid) | Zep DMR, LongMemEval-style | ✅ |
| `aegis` | ERF graph + hybrid fact retrieval | Your system | ✅ |

Run all three on the same `run-id`:

```bash
for b in flat_rag session_summary aegis; do
  python3 benchmarks/run_retrieval.py --backend $b --limit 10 --run-id dev
done
```

`session_summary` costs **one LLM call per session** at ingest (fair middle ground vs graph extraction).

## Tier 2 — Literature reference (cite, don’t re-run yet)

| System | Report from | Notes |
|--------|-------------|-------|
| **Zep / Graphiti** | [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) | Full LongMemEval; not same stack as yours |
| **MemGPT** | [Packer et al.](https://arxiv.org/abs/2310.09160) | Zep couldn’t run LongMemEval on MemGPT either |
| **Full-context** | LongMemEval paper | ~115k tokens/question; model-dependent upper bound |

Put these in **Related work** with a table: “our harness vs published results (different n, setup).”

## Tier 3 — Future backends (strongest)

| Backend | Effort | Why |
|---------|--------|-----|
| **Graphiti (local OSS)** | High | Closest head-to-head with Zep paper |
| **flat_rag + embeddings only** | Low | Strengthen turn baseline without summaries |
| **MemGPT on LongMemEval** | Very high | Integration pain |

## What’s “stupid” vs “fair”

| Baseline | Verdict |
|----------|---------|
| BM25 turns only | **Floor** — include but don’t lead the article with it |
| Session-summary RAG | **Fair** — standard in memory papers |
| Aegis vs session_summary | **Main comparison** for “is the graph worth it over summarization?” |
| Zep numbers copy-pasted | **Not a comparison** — citation only |

## Article framing

> We compare Aegis against **session-summary RAG** (LongMemEval/Zep-style) and **turn-level BM25** on LongMemEval-S (n=…).

That is defensible. “We beat BM25” alone is not.
