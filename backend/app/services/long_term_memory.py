"""Long-Term Memory Store service (Milestone 5, Phase 2.2).

A reusable, tenant-scoped store for *important* memories that must persist
independently of conversation history -- preferences, facts, instructions, and
other durable knowledge that survives across sessions and conversations.

It reuses existing architecture and never duplicates services:

* **RepositoryFactory** / **TenantAwareRepository** -- every read/write goes
  through the tenant-scoped repository, so memories are *always* filtered by
  ``organization_id``. Tenant isolation is inherited, not re-implemented.
* **Vector storage architecture** -- memories carry a dense ``embedding``
  column (Postgres ``float[]``, mirrored from ``DocumentChunk.embedding``) that
  is populated by the existing deterministic local embedder. Semantic retrieval
  over this column is implemented in Phase 2.3 (see ``semantic_memory.py`` and
  ``retrieve_semantic``) *without* a new vector database: candidates are ranked
  in Python by cosine similarity over the existing column.
* **ConversationMemoryService** -- complements short-term conversation history;
  long-term memory is the durable layer beneath it.

Deliverables for Phase 2.2:
1. ``create_memory`` -- persist a new memory (scoped to the organization).
2. ``update_memory`` -- mutate an existing memory (tenant-checked).
3. ``delete_memory`` -- remove a memory (tenant-checked).
4. ``get_memory`` / ``list_memories`` / ``get_by_key`` / ``search_by_content``
   -- retrieve memories (non-semantic: key, category, keyword).

Semantic (vector) retrieval is provided by Phase 2.3: ``retrieve_semantic`` /
``retrieve_semantic_scored`` (and the standalone ``SemanticMemoryRetriever``).
It reuses the ``embedding`` column populated at write time and ranks by cosine
similarity; it requires no new vector database.

Explicitly out of scope for Phase 2.2 (reserved columns/fields exist for them):
* importance-based ranking (``importance`` column reserved, unused)
* consolidation (``meta`` column reserved, unused)
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.models.all_models import Memory
from app.repositories.tenant_repository import RepositoryFactory
from app.services.embeddings import LocalDeterministicEmbedder
from app.services.semantic_memory import SemanticMemoryRetriever

logger = get_logger(__name__)


class LongTermMemoryService:
    """Tenant-scoped long-term memory store."""

    def __init__(
        self,
        db_session,
        organization_id: UUID,
        embedder=None,
    ):
        """Initialize with a DB session and the owning organization for scoping.

        Args:
            db_session: SQLAlchemy database session.
            organization_id: UUID of the organization (tenant key).
            embedder: Optional embedder for the ``embedding`` column. Defaults
                to the offline deterministic local embedder so the vector-store
                architecture is reused without external API keys.
        """
        self.db = db_session
        self.organization_id = organization_id
        self.repository_factory = RepositoryFactory(db_session, organization_id)
        self._embedder = embedder or LocalDeterministicEmbedder()

    # --- Create -----------------------------------------------------------

    def create_memory(
        self,
        content: str,
        category: Optional[str] = None,
        key: Optional[str] = None,
        importance: int = 0,
        agent_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> Memory:
        """Create a new long-term memory scoped to this organization.

        Args:
            content: The memory text (required).
            category: Optional grouping label (e.g. 'fact', 'preference').
            key: Optional stable per-tenant lookup key.
            importance: Reserved for later ranking (column only, no ranking yet).
            agent_id: Optional agent this memory is associated with.
            user_id: Optional user this memory is associated with.
            metadata: Optional JSON metadata (reserved for later phases).

        Returns:
            The created ``Memory`` instance.

        Raises:
            ValueError: If ``content`` is empty, or if ``key`` already exists
                within this tenant.
        """
        if not content or not content.strip():
            raise ValueError("Memory content must not be empty")

        repo = self.repository_factory.memories()

        if key:
            existing = repo.get_by_key(key)
            if existing is not None:
                raise ValueError(
                    f"A memory with key '{key}' already exists in this organization"
                )

        memory = Memory(
            organization_id=self.organization_id,
            content=content,
            category=category,
            key=key,
            importance=importance,
            agent_id=agent_id,
            user_id=user_id,
            metadata=metadata,
        )
        # Reuse the vector-storage architecture: persist a dense embedding so
        # Phase 2.3 semantic retrieval can rank without a backfill migration.
        memory.embedding = self._embedder.embed([content])[0]

        created = repo.create(memory)
        logger.info(
            "long_term_memory_created",
            memory_id=str(created.id),
            organization_id=str(self.organization_id),
            category=category,
            key=key,
        )
        return created

    # --- Read -------------------------------------------------------------

    def get_memory(self, memory_id: UUID) -> Optional[Memory]:
        """Get a single memory by ID (None if absent or not in this tenant)."""
        return self.repository_factory.memories().get(memory_id)

    def get_by_key(self, key: str) -> Optional[Memory]:
        """Get a memory by its stable per-tenant key (None if absent)."""
        return self.repository_factory.memories().get_by_key(key)

    def list_memories(
        self,
        category: Optional[str] = None,
        key: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Memory]:
        """List memories for this tenant, optionally filtered by category/key.

        Non-semantic retrieval (Phase 2.3 adds vector ranking on top).
        """
        return self.repository_factory.memories().list_memories(
            category=category, key=key, limit=limit, offset=offset
        )

    def get_by_category(self, category: str) -> List[Memory]:
        """List all memories in this tenant with the given category."""
        return self.repository_factory.memories().get_by_category(category)

    def search_by_content(self, query: str) -> List[Memory]:
        """Keyword (non-semantic) substring search over memory content.

        Complements (does not replace) semantic retrieval added in Phase 2.3;
        the two retrieval paths coexist and can be used together.
        """
        return self.repository_factory.memories().search_content(query)

    # --- Semantic retrieval (Phase 2.3) -----------------------------------

    def retrieve_semantic(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = -1.0,
        category: Optional[str] = None,
        agent_id: Optional[UUID] = None,
    ) -> List[Memory]:
        """Semantic (vector) retrieval over this tenant's long-term memories.

        Phase 2.3: ranks memories by cosine similarity of the query to each
        memory's ``embedding`` (written in Phase 2.2) and returns the top-K most
        relevant memories. Tenant isolation and the write-time embedder are
        reused (the same ``LocalDeterministicEmbedder`` instance that stored the
        vectors), so **no new vector database is created** and scores stay
        consistent with storage.

        ``min_similarity`` is an optional relevance floor (default ``-1.0`` so
        the top-K path always returns the K best-ranked memories; pass a higher
        value to drop weakly/negatively correlated matches).

        Thin wrapper over ``SemanticMemoryRetriever`` -- kept here so existing
        holders of this service get semantic retrieval for free.
        """
        retriever = SemanticMemoryRetriever(
            self.db, self.organization_id, embedder=self._embedder
        )
        return retriever.retrieve(
            query,
            top_k=top_k,
            min_similarity=min_similarity,
            category=category,
            agent_id=agent_id,
        )

    def retrieve_semantic_scored(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = -1.0,
        category: Optional[str] = None,
        agent_id: Optional[UUID] = None,
    ) -> List[tuple]:
        """Like ``retrieve_semantic`` but returns ``(Memory, score)`` pairs."""
        retriever = SemanticMemoryRetriever(
            self.db, self.organization_id, embedder=self._embedder
        )
        return retriever.retrieve_scored(
            query,
            top_k=top_k,
            min_similarity=min_similarity,
            category=category,
            agent_id=agent_id,
        )

    def count(self) -> int:
        """Count memories in this tenant."""
        return self.repository_factory.memories().count()

    # --- Update -----------------------------------------------------------

    def update_memory(
        self,
        memory_id: UUID,
        content: Optional[str] = None,
        category: Optional[str] = None,
        key: Optional[str] = None,
        importance: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Memory]:
        """Update an existing memory (tenant-checked).

        Only fields passed as non-``None`` are changed. If ``content`` changes,
        the dense ``embedding`` is recomputed so the vector stays in sync.

        Returns:
            The updated ``Memory``, or ``None`` if it does not exist / is not in
            this tenant.

        Raises:
            ValueError: If ``content`` is set to empty, or if ``key`` collides
                with another memory in this tenant.
        """
        repo = self.repository_factory.memories()
        memory = repo.get(memory_id)
        if memory is None:
            return None

        if content is not None:
            if not content.strip():
                raise ValueError("Memory content must not be empty")
            memory.content = content
            # Recompute the embedding to keep the vector store consistent.
            memory.embedding = self._embedder.embed([content])[0]

        if category is not None:
            memory.category = category

        if key is not None and key != memory.key:
            colliding = repo.get_by_key(key)
            if colliding is not None and colliding.id != memory.id:
                raise ValueError(
                    f"A memory with key '{key}' already exists in this organization"
                )
            memory.key = key

        if importance is not None:
            memory.importance = importance

        if metadata is not None:
            memory.meta = metadata

        updated = repo.update(memory)
        logger.info(
            "long_term_memory_updated",
            memory_id=str(memory_id),
            organization_id=str(self.organization_id),
        )
        return updated

    # --- Delete -----------------------------------------------------------

    def delete_memory(self, memory_id: UUID) -> bool:
        """Delete a memory (tenant-checked).

        Returns:
            ``True`` if a memory was deleted, ``False`` if it did not exist / is
            not in this tenant.
        """
        repo = self.repository_factory.memories()
        memory = repo.get(memory_id)
        if memory is None:
            return False
        repo.delete(memory)
        logger.info(
            "long_term_memory_deleted",
            memory_id=str(memory_id),
            organization_id=str(self.organization_id),
        )
        return True


# Convenience function for dependency injection
def get_long_term_memory_service(db_session, organization_id: UUID) -> LongTermMemoryService:
    """Factory function to create a LongTermMemoryService instance."""
    return LongTermMemoryService(db_session, organization_id)


__all__ = [
    "LongTermMemoryService",
    "get_long_term_memory_service",
]
