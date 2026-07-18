"""Embedding providers for vector storage & RAG retrieval (Milestone 3).

Provides a pluggable ``EmbeddingProvider`` interface plus two implementations:

* ``LocalDeterministicEmbedder`` -- a pure-Python, dependency-free embedder used
  for development, tests, and offline operation. It is deterministic (same text
  -> same vector) and produces L2-normalized vectors so cosine similarity is a
  meaningful ranking signal. It is NOT a semantic model; it is a stand-in that
  lets the full ingest -> embed -> retrieve pipeline run without external API
  keys.
* ``OpenAICompatibleEmbedder`` -- calls an OpenAI-compatible embeddings endpoint
  (OpenAI or OpenRouter) when an API key is configured. Used in production.

``get_embedding_provider`` selects the provider from the knowledge base's
``embedding_model`` / settings, falling back to the local embedder when no key
is available so the pipeline stays testable offline.

Vectors are stored on ``DocumentChunk.embedding`` (a Postgres ``float[]`` column)
and similarity is computed in Python (cosine). This avoids a pgvector dependency
for the milestone; ADR-003 describes the production pgvector/ChromaDB upgrade.
"""
import hashlib
import math
from typing import List, Optional, Protocol

import httpx

# Dimension for the local deterministic embedder. Kept modest so array storage
# and Python cosine stay cheap in tests while still being a real dense vector.
_LOCAL_DIM = 256


class EmbeddingProvider(Protocol):
    """Minimal embedding contract used by the ingestion/retrieval pipeline."""

    dimensions: int

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Return one dense vector per input string."""
        ...


def _tokenize(text: str) -> List[str]:
    """Lowercase and split into character 3-grams (hashing-trick input)."""
    low = (text or "").lower()
    clean = "".join(ch if ch.isalnum() or ch == " " else " " for ch in low)
    grams = [clean[i : i + 3] for i in range(len(clean) - 2)]
    return grams or [clean]


class LocalDeterministicEmbedder:
    """Hashing-trick embedder: deterministic, normalized, dependency-free."""

    def __init__(self, dimensions: int = _LOCAL_DIM):
        self.dimensions = dimensions

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self.dimensions
        for tok in _tokenize(text):
            h = hashlib.md5(tok.encode("utf-8"), usedforsecurity=False).digest()
            # Two independent hash halves pick a position and a sign.
            pos = int.from_bytes(h[:4], "big") % self.dimensions
            sign = 1.0 if h[4] & 1 else -1.0
            weight = 1.0 + (int.from_bytes(h[5:8], "big") % 100) / 100.0
            vec[pos] += sign * weight
        # L2 normalize so cosine similarity is a clean [0, 1] ranking signal.
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


class OpenAICompatibleEmbedder:
    """Embedder for any OpenAI-compatible ``/embeddings`` endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        dimensions: Optional[int] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        # OpenAI text-embedding-3-small is 1536-d; allow an override.
        return self._dimensions or 1536

    def embed(self, texts: List[str]) -> List[List[float]]:
        payload: dict = {"input": texts, "model": self.model}
        if self._dimensions:
            payload["dimensions"] = self._dimensions
        resp = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in data]


def get_embedding_provider(kb, settings) -> EmbeddingProvider:
    """Select an embedding provider for a knowledge base.

    Defaults to the local deterministic embedder (offline, no API key). Only an
    OpenAI-compatible provider is used when ``EMBEDDINGS_PROVIDER`` is set to
    ``"openai"``/``"openrouter"`` AND a corresponding API key is configured;
    otherwise it falls back to local so the pipeline always runs.
    """
    provider_name = (getattr(settings, "EMBEDDINGS_PROVIDER", "local") or "local").lower()
    if provider_name in ("openai", "openrouter"):
        api_key = settings.OPENAI_API_KEY or settings.OPENROUTER_API_KEY
        if api_key:
            model = getattr(kb, "embedding_model", None) or "text-embedding-3-small"
            base = (
                getattr(settings, "OPENAI_API_BASE_URL", None)
                or settings.OPENROUTER_BASE_URL
            )
            return OpenAICompatibleEmbedder(
                api_key=api_key, model=model, base_url=base
            )
    return LocalDeterministicEmbedder()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors (0.0 on mismatch)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


__all__ = [
    "EmbeddingProvider",
    "LocalDeterministicEmbedder",
    "OpenAICompatibleEmbedder",
    "get_embedding_provider",
    "cosine_similarity",
]
