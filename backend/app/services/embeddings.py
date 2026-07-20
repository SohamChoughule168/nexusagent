"""Embedding providers for vector storage & RAG retrieval (Milestone 3 + B).

Provides a pluggable ``EmbeddingProvider`` interface plus implementations:

* ``LocalDeterministicEmbedder`` -- pure-Python, dependency-free embedder for
  development, tests, and offline operation. Deterministic, L2-normalized.
  NOT semantic; a stand-in that lets the pipeline run without external keys.
* ``OpenAICompatibleEmbedder`` -- any OpenAI-compatible ``/embeddings`` endpoint
  (OpenAI, OpenRouter, Azure OpenAI, Ollama's ``/v1`` shim). Used in production.
* ``GeminiEmbedder`` -- Google Gemini ``batchEmbedContents`` endpoint.

``get_embedding_provider`` selects the provider from ``EMBEDDINGS_PROVIDER``
(+ the KB's ``embedding_model`` / settings), falling back to the local embedder
when no key is available so the pipeline stays testable offline.

Vectors are stored on ``DocumentChunk.embedding`` (a Postgres ``float[]`` column)
and similarity is computed in Python (cosine). ADR-003 describes the production
pgvector/ChromaDB upgrade.
"""
import hashlib
import json
import math
from typing import List, Optional, Protocol

import httpx

# Dimension for the local deterministic embedder.
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
            pos = int.from_bytes(h[:4], "big") % self.dimensions
            sign = 1.0 if h[4] & 1 else -1.0
            weight = 1.0 + (int.from_bytes(h[5:8], "big") % 100) / 100.0
            vec[pos] += sign * weight
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
        headers: Optional[dict] = None,
        embeddings_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._dimensions = dimensions
        self._headers = headers or {}
        self._embeddings_url = embeddings_url or f"{self.base_url}/embeddings"

    @property
    def dimensions(self) -> int:
        return self._dimensions or 1536

    def embed(self, texts: List[str]) -> List[List[float]]:
        payload: dict = {"input": texts, "model": self.model}
        if self._dimensions:
            payload["dimensions"] = self._dimensions
        resp = httpx.post(
            self._embeddings_url,
            headers={"Authorization": f"Bearer {self.api_key}", **self._headers},
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in data]


class GeminiEmbedder:
    """Google Gemini embeddings via ``batchEmbedContents``."""

    def __init__(self, api_key: str, model: str, base_url: str = "https://generativelanguage.googleapis.com"):
        self.api_key = api_key
        self.model = model or "text-embedding-004"
        self.base_url = base_url.rstrip("/")

    @property
    def dimensions(self) -> int:
        # Gemini text-embedding-004 is 768-d; configurable models may differ.
        return 768

    def embed(self, texts: List[str]) -> List[List[float]]:
        url = f"{self.base_url}/v1beta/models/{self.model}:batchEmbedContents?key={self.api_key}"
        requests = [
            {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
        resp = httpx.post(url, json={"requests": requests}, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        return [e["values"] for e in data.get("embeddings", [])]


def get_embedding_provider(kb, settings) -> EmbeddingProvider:
    """Select an embedding provider for a knowledge base.

    Defaults to the local deterministic embedder (offline, no API key). A
    remote provider is used only when ``EMBEDDINGS_PROVIDER`` selects it AND the
    required credentials are configured; otherwise it falls back to local so the
    pipeline always runs.
    """
    provider_name = (getattr(settings, "EMBEDDINGS_PROVIDER", "local") or "local").lower()
    kb_model = getattr(kb, "embedding_model", None)

    def _local():
        return LocalDeterministicEmbedder()

    if provider_name in ("openai", "openrouter"):
        api_key = settings.OPENAI_API_KEY or settings.OPENROUTER_API_KEY
        if api_key:
            base = getattr(settings, "OPENAI_BASE_URL", None) or settings.OPENROUTER_BASE_URL
            return OpenAICompatibleEmbedder(
                api_key=api_key,
                model=kb_model or "text-embedding-3-small",
                base_url=base,
            )
        return _local()

    if provider_name == "azure":
        if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_DEPLOYMENT:
            embed_url = (
                f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/"
                f"{settings.AZURE_OPENAI_DEPLOYMENT}/embeddings?api-version={settings.AZURE_OPENAI_API_VERSION}"
            )
            return OpenAICompatibleEmbedder(
                api_key=settings.AZURE_OPENAI_API_KEY,
                model=settings.AZURE_OPENAI_DEPLOYMENT,
                base_url=settings.AZURE_OPENAI_ENDPOINT,
                embeddings_url=embed_url,
                headers={"api-key": settings.AZURE_OPENAI_API_KEY},
            )
        return _local()

    if provider_name == "gemini":
        if settings.GEMINI_API_KEY:
            return GeminiEmbedder(
                api_key=settings.GEMINI_API_KEY,
                model=kb_model or "text-embedding-004",
                base_url=settings.GEMINI_BASE_URL,
            )
        return _local()

    if provider_name == "ollama":
        return OpenAICompatibleEmbedder(
            api_key="",
            model=settings.OLLAMA_EMBED_MODEL or "nomic-embed-text",
            base_url=f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1",
        )

    return _local()


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
    "GeminiEmbedder",
    "get_embedding_provider",
    "cosine_similarity",
]
