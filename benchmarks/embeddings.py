"""Benchmark embedding env helpers (re-exports scripts.embeddings)."""
from scripts.embeddings import (  # noqa: F401
    apply_embedding_env,
    embedding_dimensions,
    local_embed_fn,
    litellm_embed_fn,
    make_embed_fn,
)
