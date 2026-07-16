"""Semantic retrieval for long-term memories (Milestone 5, Phase 2.3).

Adds *vector retrieval* over the ``Memory.embedding`` column that Phase 2.2
already populated -- **without** standing up another vector database.

Design / reuse (no duplication):
* ``RepositoryFactory`` -> ``memories()`` -- every candidate is fetched through
  the tenant-scoped repository, so retrieval inherits the *exact* same
  ``organization_id`` isolation as the CRUD path. Tenant isolation is reused,
  not re-implemented.
* ``app.services.embeddings`` -- reuses the *same* ``LocalDeterministicEmbedder``
  that Phase 2.2 used to write the ``embedding`` column, and the existing
  ``cosine_similarity`` function for ranking. Same vector model at read time as
  at write time => scores are meaningful.
* **No new vector database** -- we rank in Python over the existing ``float[]``
  column, exactly like ``app.services.rag`` ranks ``DocumentChunk`` embeddings.

The retriever is intentionally decoupled from ``LongTermMemoryService`` so any
consumer can use it directly (reusable by later phases without touching
storage):
* Chat (``conversations`` endpoint) -- enrich the prompt with recalled memories.
* Agent Orchestrator -- recall durable facts/preferences mid-plan.
* Multi-Agent Router -- ground routing decisions in long-term memory context.
* Future Function Calling -- ground tool selection in long-term memory.

``LongTermMemoryService`` also exposes a thin ``retrieve_semantic`` wrapper so
existing holders of that service get semantic retrieval for free, reusing the
service's own embedder instance (keeping write/read vector models identical).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.models.all_models import Memory
from app.repositories.tenant_repository import RepositoryFactory
from app.services.embeddings import LocalDeterministicEmbedder, cosine_similarity

# A (memory, similarity) pair, ranked descending by similarity.
ScoredMemory = Tuple[Memory, float]


class SemanticMemoryRetriever:
    """Tenant-scoped semantic retrieval over long-term memories.

    Pure read path: it never creates, mutates, or deletes memories, and never
    touches the Conversation Memory service, so it cannot regress existing
    storage or short-term-memory logic.
    """

    def __init__(self, db_session, organization_id, embedder=None):
        """Initialize with a DB session, the owning organization, and embedder.

        Args:
            db_session: SQLAlchemy database session.
            organization_id: UUID of the organization (tenant key). All
                candidates are fetched tenant-scoped via ``RepositoryFactory``.
            embedder: Optional embedder for the query vector. Defaults to the
                offline deterministic local embedder so it matches the model
                Phase 2.2 used to write ``Memory.embedding``.
        """
        self.db = db_session
        self.organization_id = organization_id
        self.repository_factory = RepositoryFactory(db_session, organization_id)
        # Reuse the deterministic local embedder (matches the writer's model so
        # cosine scores are comparable to the stored vectors).
        self._embedder = embedder or LocalDeterministicEmbedder()

    def retrieve_scored(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = -1.0,
        category: Optional[str] = None,
        agent_id=None,
    ) -> List[ScoredMemory]:
        """Return up to ``top_k`` (memory, score) pairs ranked by similarity.

        Candidates are pulled from this tenant only (``RepositoryFactory``
        enforces isolation) and filtered to those carrying an ``embedding``.
        The query is embedded with the reused provider, scored with
        ``cosine_similarity``, filtered by ``min_similarity``, sorted
        descending, and truncated to ``top_k``.

        ``min_similarity`` is an optional *relevance floor* for callers that
        want to enforce a quality bar; it defaults to ``-1.0`` so the top-K
        path always surfaces the K best-ranked memories even when every
        candidate scores weakly (the deterministic local embedder can yield
        slightly negative cosine for unrelated text). Pass a higher value (e.g.
        ``0.0``) to drop weakly/negatively correlated memories.

        Returns:
            List of ``(Memory, float)`` tuples, highest similarity first. Empty
            when there are no embedded memories, the query is blank, or nothing
            clears ``min_similarity``.
        """
        repo = self.repository_factory.memories()
        candidates = repo.list_memories(category=category)
        if agent_id is not None:
            candidates = [m for m in candidates if m.agent_id == agent_id]
        embedded = [m for m in candidates if getattr(m, "embedding", None)]

        if not embedded or not query or not query.strip():
            return []

        (query_vec,) = self._embedder.embed([query])
        scored = [
            (cosine_similarity(query_vec, m.embedding), m) for m in embedded
        ]
        # Drop anything below the relevance floor, then rank descending.
        scored = [(s, m) for s, m in scored if s >= min_similarity]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = -1.0,
        category: Optional[str] = None,
        agent_id=None,
    ) -> List[Memory]:
        """Convenience: return only the ranked ``Memory`` objects (no scores)."""
        return [
            m
            for _, m in self.retrieve_scored(
                query, top_k, min_similarity, category, agent_id
            )
        ]

    def format_for_prompt(
        self,
        memories: List[Memory],
        max_chars: int = 4000,
    ) -> str:
        """Render retrieved memories as a single context block for a prompt.

        Reused by Chat / Orchestrator / Router to inject recalled durable
        memory into a generation prompt. Empty input yields an empty string so
        callers can skip injection when there is nothing to recall.
        """
        if not memories:
            return ""
        parts: List[str] = []
        total = 0
        for i, m in enumerate(memories, start=1):
            snippet = (m.content or "")[:max_chars]
            # Always emit at least the first memory even if it alone is huge.
            if total + len(snippet) > max_chars and parts:
                break
            total += len(snippet)
            label = f"[{m.category}] " if m.category else ""
            parts.append(f"Memory {i}: {label}{snippet}")
        return "\n".join(parts)


# Convenience factory for dependency injection
def get_semantic_memory_retriever(
    db_session, organization_id
) -> SemanticMemoryRetriever:
    """Factory function to create a SemanticMemoryRetriever instance."""
    return SemanticMemoryRetriever(db_session, organization_id)


__all__ = [
    "SemanticMemoryRetriever",
    "ScoredMemory",
    "get_semantic_memory_retriever",
]
