# When Is Graph Memory Worth the Cost?

**A decision framework for structured agent memory vs flat RAG**

Aegis Technical Whitepaper · v0.1 · June 2026  
**Author:** Identiti / Aegis  
**Status:** Pilot evaluation (LongMemEval-S dev slice, n=10)  
**Companion data:** [EVAL_REPORT.md](EVAL_REPORT.md) · [reference/](reference/)

---

## Executive summary

Teams building long-horizon AI agents face a design choice: **store raw conversations and search them** (flat RAG), or **extract structured memory into a temporal knowledge graph** (graph memory, e.g. Zep-style ERF).

On a controlled benchmark slice, we find:

| Dimension | Flat BM25 RAG | Aegis graph memory |
|-----------|---------------|------------------|
| **Ingest cost** | ~$0 (index turns) | **LLM extraction per session** |
| **Retrieval latency** | **~28 ms** | ~200 ms (~1.4 s avg incl. cold start) |
| **Session recall@10** | 1.00 | 1.00 |
| **Session ranking (NDCG@10)** | **0.96** | 0.75 |
| **End-to-end QA accuracy** | 70% | **80%** |
| **Temporal “as-of” queries** | No | **Yes** |
| **Contradiction / provenance** | No | **Yes** |

**Bottom line:** Graph memory costs more at write time and is slower at read time, but can **improve answer quality even when session-level retrieval metrics look worse**. It is worth the cost when downstream QA quality, temporal correctness, and structured memory matter more than minimum latency and zero ingest cost.

---

## 1. The problem

Production agents must remember facts across **many sessions** (LongMemEval averages ~115k tokens of history per question). Context windows alone do not scale; some form of **external memory** is required.

The default approach is **flat RAG**: chunk or turn-index conversation text, retrieve by BM25 or embeddings, paste into the prompt. It is simple, fast, and cheap to ingest.

The alternative is **graph memory**: LLM extraction → entities and facts → temporal graph → hybrid retrieval → structured context for the reader model.

The question for product and engineering leaders is not “which is more elegant?” but:

> **When does the extra ingest cost and latency pay for itself in answer quality and capability?**

---

## 2. Two architectures

### 2.1 Flat RAG (baseline)

```
Sessions → tokenize turns → BM25 index (in memory)
Query    → top-k turns    → paste into LLM prompt
```

- **Ingest:** O(1) per turn (no LLM)
- **Retrieve:** keyword overlap over raw dialogue
- **Strength:** gold answer turn often ranks #1
- **Weakness:** noisy context, no time travel, no contradiction handling

### 2.2 Graph memory (Aegis)

```
Sessions → LLM extract entities/facts → Neo4j ERF graph
         → temporal bounds, contradiction expiry, communities
Query    → hybrid BM25 + vectors + BFS → <FACTS> + <ENTITIES> context
```

- **Ingest:** multiple LLM calls per session (extraction, resolution, temporal)
- **Retrieve:** fact-level search, map facts → source sessions
- **Strength:** compressed factual context, bi-temporal `as_of`, provenance
- **Weakness:** higher cost, higher latency, session ranking can lag flat RAG

*Aegis implements a Zep-aligned Entity–Relation–Fact pipeline with per-user encryption, open-source benchmark harness, and local embedding support (BGE).*

---

## 3. Cost model

Numbers below are **order-of-magnitude** for planning; pilot measured retrieval latency, ingest cost is modeled.

### 3.1 Ingest cost

| | Flat RAG | Aegis graph |
|--|----------|-------------|
| **LLM calls per session** | 0 | ~3–6 (entities, facts, resolve, temporal, community batch) |
| **Typical LongMemEval instance** | ~40 sessions / question | same |
| **Ingest for one benchmark question** | negligible | ~120–240 LLM calls (one-time per instance) |
| **Production chat message** | append to index | 1 pipeline run (~3–6 fast-model calls) |

**Rule of thumb:** If you ingest **S sessions/day** with Haiku-class models at ~$0.001–0.01 per extraction call (varies by transcript length), graph ingest is **O(S × calls × price)**. Flat RAG ingest is **storage only**.

**Break-even intuition:** Graph memory pays off when **each stored session is queried multiple times** or when **wrong answers are expensive** (support, health, finance, personal assistant retention).

### 3.2 Storage cost

| | Flat RAG | Aegis |
|--|----------|-------|
| **Store** | Turn text (Redis / vector DB) | Neo4j nodes + FACT edges + optional embeddings |
| **Per-user scale** | linear in total characters | linear in extracted facts (often ≪ raw text) |
| **Ops complexity** | low | medium (graph DB, indexes, backfill) |

Extracted graphs can be **smaller than raw logs** for retrieval (facts vs full transcripts) but add **index maintenance** (full-text + vector).

### 3.3 Query cost & latency

**Measured on dev slice (n=10, LongMemEval-S):**

| Metric | flat_rag | Aegis |
|--------|----------|-------|
| Retrieval p50 | ~28 ms | ~160 ms |
| Retrieval p95 | ~30 ms | ~740 ms |
| Retrieval max | ~30 ms | ~12 s (embedding model cold start, Q1) |
| QA reader | same model both | same model both |

Flat RAG is **~7× faster** at retrieval on this hardware. After embedding warm-up, Aegis is typically **100–300 ms** — acceptable for chat, not for sub-10 ms lookup.

**Query LLM cost:** Both systems feed a reader model; Aegis context is often **shorter and more structured** (facts vs 20 turns), which can **reduce reader tokens** — a partial offset to ingest cost.

---

## 4. Capability matrix

| Capability | Flat RAG | Graph memory |
|------------|----------|--------------|
| Keyword session retrieval | ✅ Strong | ✅ Strong (recall@10 = 1.0 pilot) |
| Gold session at rank 1 | ✅ **8/10** | ⚠️ 5/10 |
| End-to-end QA (pilot) | 70% | ✅ **80%** |
| “What was true on date X?” | ❌ | ✅ `as_of` bi-temporal filter |
| Fact invalidation / updates | ❌ | ✅ contradict + expire |
| Structured export (wallet, API) | ❌ | ✅ entities + facts JSON |
| Per-user encryption | optional | ✅ built-in |
| Ingest LLM cost | ✅ none | ❌ required |
| Minimal ops stack | ✅ | ❌ Neo4j + pipeline |

---

## 5. Evaluation summary (pilot, n=10)

Full tables: [EVAL_REPORT.md](EVAL_REPORT.md)

### 5.1 Retrieval

- **Recall@10:** 1.00 vs 1.00 — both find the gold session in top 10.
- **NDCG@10:** 0.96 vs 0.75 — flat RAG ranks the correct session higher.
- **Recall@5:** 1.00 vs 0.90 — one Aegis case (`c5e8278d`) had gold at rank 6.

### 5.2 End-to-end QA

Same reader and judge (`claude-haiku-4-5`):

- **flat_rag:** 7/10 correct  
- **Aegis:** 8/10 correct  

**Decisive case — `58bf7951`:**  
Both systems had **recall@10 = 1.0**. Flat RAG ranked the gold session **#1** but the reader **failed** (“play name not in memory”). Aegis returned an explicit fact (`User ATTENDED The Glass Menagerie`) and **answered correctly**.

**Shared failures — `51a45a95`, `58ef2f1c`:**  
Both systems failed QA. Graph memory does not fix bad extraction or missing facts in the haystack.

### 5.3 Interpretation

Session-level metrics **understate** graph memory value when the consumer is an LLM reading **formatted facts**, not raw turns.  
Session-level metrics **overstate** flat RAG when rank-1 turns still produce wrong answers.

---

## 6. Decision framework

Use this flowchart logic when choosing (or combining) approaches.

### 6.1 Choose **flat RAG** when:

- ✅ Prototype / MVP; minimal infra  
- ✅ Ingest cost must be **~zero** (no LLM on write)  
- ✅ Retrieval latency **< 50 ms** is hard requirement  
- ✅ Queries are mostly **lexical** (“find the message where I said X”)  
- ✅ No need for **point-in-time** memory (“what did we know before Y?”)  
- ✅ Wrong answers are low stakes; user can scroll raw chat  

### 6.2 Choose **graph memory** when:

- ✅ **Answer quality** matters more than session rank  
- ✅ Users have **long histories** (many sessions) and reuse old facts  
- ✅ You need **temporal queries** (valid_from / valid_to, as-of)  
- ✅ Facts **change** (job, address, preferences) and contradictions must resolve  
- ✅ Downstream products need **structured memory** (profile, wallet, API, MCP)  
- ✅ **Compliance / provenance** (which session asserted this fact?)  
- ✅ Ingest LLM cost is acceptable amortized over many reads  

### 6.3 Hybrid (recommended production path)

Many deployments should use **both**:

| Layer | Role |
|-------|------|
| **Graph memory** | Canonical facts, temporal state, user profile |
| **Flat / episodic RAG** | Recent verbatim turns, quote-level fidelity |
| **Reader prompt** | Facts first, recent dialogue second |

Aegis already supports episodic context during extraction and Redis conversation history at chat time; the hybrid is natural.

### 6.4 Scorecard (qualitative)

Rate your product 1–5 on each axis; **≥18 total** on graph-weighted rows suggests graph memory is worth piloting.

| Criterion | Weight | Your score (1–5) |
|-----------|--------|------------------|
| Long-horizon memory (>10 sessions) | ×3 | |
| Cost of wrong answer | ×3 | |
| Need temporal / as-of correctness | ×3 | |
| Structured export / API | ×2 | |
| Query volume >> ingest volume | ×2 | |
| Latency budget > 200 ms OK | ×1 | |
| Tight ingest budget | ×1 (inverse) | |

---

## 7. Risks and limitations

**Pilot scale:** n=10 questions; scale to 50–100+ before investor or academic claims.  

**Extraction errors:** Graph memory is only as good as extraction; garbage in → structured garbage out.  

**Ranking gap:** Session NDCG may lag flat RAG until session-aware reranking (episode boost, cross-encoder).  

**Ops:** Neo4j, embedding indexes, backfill jobs add operational surface.  

**Cost drift:** Extraction calls scale with session count; monitor tokens per user per day.

---

## 8. Roadmap & validation plan

| Milestone | Purpose |
|-----------|---------|
| **100-question eval** | Narrow confidence intervals on QA and NDCG |
| **Ablation study** | embeddings, communities, `as_of`, reranker |
| **Session reranker** | Close NDCG gap without losing QA |
| **Cost dashboard** | ingest $/user/month vs flat baseline |
| **Hybrid chat mode** | facts + recent turns in production `/chat` |

Reproduce pilot:

```bash
cd aegis
python3 benchmarks/run_retrieval.py --backend aegis --limit 10 --run-id dev --backfill-embeddings
python3 benchmarks/run_retrieval.py --backend flat_rag --limit 10 --run-id dev
python3 benchmarks/run_qa.py --backend aegis --limit 10 --run-id dev --backfill-embeddings
python3 benchmarks/run_qa.py --backend flat_rag --limit 10 --run-id dev
python3 benchmarks/compare_results.py --run-id dev
```

---

## 9. Conclusion

**Graph memory is not free.** It adds LLM cost at ingest, infrastructure at store, and milliseconds (or more) at retrieve.

**Graph memory is worth it when:**

1. The agent must **answer correctly**, not merely **find the right chat**.  
2. Memory must reflect **what was true when**, not just what was said.  
3. The product treats memory as a **durable asset** (profile, API, trust), not a log search.

Our pilot shows **parity on recall**, **lower session ranking**, and **higher QA accuracy** — the pattern we expect when the retrieval unit shifts from **turns** to **facts**. That is the trade investors and architects should evaluate against their own cost of wrong answers and their own latency budget.

---

## Appendix A — One-page leave-behind

**Aegis:** Zep-style temporal graph memory for AI agents (open pipeline + benchmark harness).

**Pilot (n=10):** recall@10 tied; NDCG flat wins; **QA +10 pp for graph**.

**Choose graph when:** long horizon, temporal correctness, structured memory, high cost of errors.

**Choose flat when:** MVP speed, zero ingest LLM, sub-50 ms retrieval.

**Contact / repo:** [your URL] · `aegis/benchmarks/WHITEPAPER.md`

---

## Appendix B — Case study excerpts

### B.1 Aegis wins despite rank (`58bf7951`)

**Question:** Which play did you attend at the community theater?  
**Gold:** The Glass Menagerie  

| System | Gold rank | QA |
|--------|-----------|-----|
| flat_rag | 1 | ✗ “play name not in memory” |
| Aegis | 1 | ✓ fact: `User ATTENDED The Glass Menagerie` |

### B.2 Both fail (`51a45a95`)

**Question:** Where did you redeem the coupon?  
**Gold:** Target  

Both retrieved relevant sessions; extraction captured “coffee creamer coupon” but not **Target**. Neither architecture rescues missing facts.

### B.3 Ranking ≠ failure (`118b2229`)

**Gold rank:** flat #1, Aegis #6 — **both answered correctly**. Lower NDCG did not block QA.

---

*This document is intended for technical investors, enterprise architects, and research partners. Numbers cite the dev slice in `benchmarks/reference/` unless noted as modeled estimates.*
