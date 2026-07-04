"""Benchmark configuration from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

BENCHMARKS_DIR = Path(__file__).resolve().parent
DATA_DIR = BENCHMARKS_DIR / "data"
RESULTS_DIR = BENCHMARKS_DIR / "results"
CHECKPOINTS_DIR = RESULTS_DIR / "checkpoints"

# Extraction / indexing (graph pipeline per session)
# Use a Groq model that exists on your account (qwen3-32b was removed from Groq).
BENCH_LLM_MODEL = os.getenv(
    "BENCH_LLM_MODEL",
    os.getenv("LLM_FAST", "groq/llama-3.3-70b-versatile"),
)

# End-to-end reader and judge (LongMemEval-style QA eval)
BENCH_READER_MODEL = os.getenv("BENCH_READER_MODEL", "anthropic/claude-3-5-sonnet-latest")
BENCH_JUDGE_MODEL = os.getenv("BENCH_JUDGE_MODEL", "anthropic/claude-3-5-sonnet-latest")

BENCH_NEO4J_DATABASE = os.getenv("BENCH_NEO4J_DATABASE", os.getenv("NEO4J_DATABASE", "neo4j"))
# Zep paper uses n=4 prior turns for entity extraction context.
BENCH_EPISODIC_TURNS = int(os.getenv("BENCH_EPISODIC_TURNS", "4"))
BENCH_RETRIEVAL_TOP_K = int(os.getenv("BENCH_RETRIEVAL_TOP_K", "20"))
BENCH_ENTITY_TOP_K = int(os.getenv("BENCH_ENTITY_TOP_K", "20"))
BENCH_RERANK_METHOD = os.getenv("BENCH_RERANK_METHOD", "rrf")
BENCH_QA_TOP_K = int(os.getenv("BENCH_QA_TOP_K", "12"))

# Groq llama-3.1-8b-instant free tier: ~6k tokens/request. Keep transcript small.
BENCH_MAX_TRANSCRIPT_CHARS = int(os.getenv("BENCH_MAX_TRANSCRIPT_CHARS", "4000"))

# Embeddings: local BGE by default (free). Set BENCH_EMBEDDING_PROVIDER=openai for API.
BENCH_ENABLE_EMBEDDINGS = os.getenv("BENCH_ENABLE_EMBEDDINGS", "1").lower() in (
    "1", "true", "yes",
)
BENCH_EMBEDDING_MODEL = os.getenv(
    "BENCH_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
)
BENCH_EMBEDDING_PROVIDER = os.getenv("BENCH_EMBEDDING_PROVIDER", "local")

# Pause between session ingests to stay under Groq TPM limits (seconds).
BENCH_INGEST_DELAY_S = float(os.getenv("BENCH_INGEST_DELAY_S", "1.5"))

DEFAULT_DATA_FILE = DATA_DIR / "longmemeval_s_cleaned.json"


def apply_benchmark_env() -> None:
    """Configure optional paid services and embeddings for benchmark runs."""
    from scripts.embeddings import apply_embedding_env

    apply_embedding_env(
        enable=BENCH_ENABLE_EMBEDDINGS,
        model=BENCH_EMBEDDING_MODEL,
        provider=BENCH_EMBEDDING_PROVIDER,
    )
