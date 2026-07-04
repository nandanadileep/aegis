"""Embedding providers: local BGE (free) or litellm API."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Callable, List, Optional

_MODEL_DIMENSIONS: dict[str, int] = {
    "bge-small-en-v1.5": 384,
    "bge-base-en-v1.5": 768,
    "bge-m3": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}


def embedding_dimensions(model: Optional[str] = None) -> int:
    model = (model or os.getenv("EMBEDDING_MODEL") or "").lower()
    for key, dim in _MODEL_DIMENSIONS.items():
        if key in model:
            return dim
    raw = os.getenv("EMBEDDING_DIMENSIONS")
    if raw:
        return int(raw)
    return 384


@lru_cache(maxsize=2)
def _load_local_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def local_embed_fn(model: Optional[str] = None) -> Callable[[List[str]], List[List[float]]]:
    model_name = model or os.getenv(
        "EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"
    )

    def _call(texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        encoder = _load_local_model(model_name)
        vectors = encoder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    return _call


def litellm_embed_fn(model: Optional[str] = None) -> Callable[[List[str]], List[List[float]]]:
    import litellm

    model_name = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    def _call(texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = litellm.embedding(model=model_name, input=texts)
        items = sorted(resp.data, key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in items]

    return _call


def make_embed_fn() -> Optional[Callable[[List[str]], List[List[float]]]]:
    if not os.getenv("EMBEDDING_MODEL"):
        return None
    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    if provider == "local":
        return local_embed_fn()
    return litellm_embed_fn()


def apply_embedding_env(
    *,
    enable: bool = True,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> None:
    if not enable:
        os.environ.pop("EMBEDDING_MODEL", None)
        return
    model = model or os.getenv("BENCH_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    provider = provider or os.getenv("BENCH_EMBEDDING_PROVIDER", "local")
    os.environ["EMBEDDING_MODEL"] = model
    os.environ["EMBEDDING_PROVIDER"] = provider
    os.environ["EMBEDDING_DIMENSIONS"] = str(embedding_dimensions(model))
