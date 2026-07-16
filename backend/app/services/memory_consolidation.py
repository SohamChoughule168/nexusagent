"""Memory Consolidation service (Milestone 5, Phase 2.4).

Detects highly similar long-term memories *within a single tenant* and merges
duplicates so the durable memory store stays clean and query-relevant.

It reuses the existing architecture and never duplicates services:

* **LongTermMemoryService** -- every read, update, and delete is delegated to
  the long-term memory service, so tenant isolation (enforced by
  ``RepositoryFactory`` / ``TenantAwareRepository``) is inherited, not
  re-implemented. Consolidation can therefore never cross tenant boundaries or
  touch another organization's memories.
* **cosine_similarity + the stored ``embedding`` column** -- duplicate detection
  reuses the exact same vectors and scoring function that Phase 2.3 semantic
  retrieval uses. No new embedding is computed and the semantic retrieval path
  (``SemanticMemoryRetriever``) is untouched.
* **LocalDeterministicEmbedder** -- reused (via the wrapped service) so scoring
  stays consistent with how memories were originally embedded at write time.

Merge semantics (one surviving memory per duplicate group):

* The **earliest-created** memory in the group becomes the *survivor* (its
  ``id`` and original ``created_at`` are preserved).
* ``importance`` is set to the **maximum** across the whole group (highest
  importance preserved).
* ``metadata`` is merged across the group -- survivor keys win conflicts, all
  other keys from duplicates are preserved.
* ``content`` is preserved from the survivor (the duplicate's text is dropped,
  never concatenated, so no noisy derived memory is created).
* ``updated_at`` reflects the consolidation time (SQLAlchemy ``onupdate``);
  ``created_at`` is untouched.
* Duplicate rows are **deleted**, never re-created -- so consolidation reduces
  the row count and never produces new duplicate memories.

Out of scope (explicitly NOT modified): semantic retrieval
(``SemanticMemoryRetriever`` / ``retrieve_semantic``) and conversation memory
(``ConversationMemoryService``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.services.embeddings import cosine_similarity
from app.services.long_term_memory import LongTermMemoryService

logger = get_logger(__name__)

# Memories at or above this cosine similarity are treated as duplicates.
# Identical content scores ~1.0 with the deterministic embedder; near-duplicate
# phrasing scores lower, so callers can tighten/loosen the boundary.
DEFAULT_SIMILARITY_THRESHOLD = 0.95


@dataclass
class DuplicatePair:
    """A detected duplicate: ``duplicate_id`` should merge into ``survivor_id``."""

    survivor_id: UUID
    duplicate_id: UUID
    similarity: float


@dataclass
class ConsolidationResult:
    """Outcome of a consolidation pass over one tenant's memories."""

    detected_pairs: int = 0  # number of duplicate memories found
    merged_count: int = 0  # number of memories deleted (merged away)
    comparisons: int = 0  # pairwise similarity comparisons performed
    remaining_count: int = 0  # memories left in the tenant afterwards


class MemoryConsolidationService:
    """Tenant-scoped detector/merger of duplicate long-term memories."""

    def __init__(
        self,
        db_session,
        organization_id: UUID,
        embedder=None,
    ):
        self.db = db_session
        self.organization_id = organization_id
        # Delegate all tenant-scoped CRUD to LongTermMemoryService so isolation
        # and the write-time embedder are reused (no duplicated logic). Every
        # operation this service performs is therefore automatically filtered by
        # organization_id via RepositoryFactory.
        self._lts = LongTermMemoryService(db_session, organization_id, embedder=embedder)
        self.repository_factory = self._lts.repository_factory

    # --- Detection (read-only) -------------------------------------------

    def find_duplicate_pairs(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        limit: int = 100,
        offset: int = 0,
    ) -> List[DuplicatePair]:
        """Return duplicate pairs within this tenant.

        Read-only: detection performs NO mutation. Memories without an embedding
        are skipped (they cannot be scored). Pairs are grouped by connectivity
        so transitive similarity (A~B, B~C) collapses into one group; within a
        group the earliest-created memory is the survivor.
        """
        memories = self._lts.list_memories(limit=limit, offset=offset)
        groups, _ = self._find_groups(memories, similarity_threshold)
        pairs: List[DuplicatePair] = []
        for idxs in groups:
            if len(idxs) < 2:
                continue
            members = [memories[i] for i in idxs]
            survivor = self._pick_survivor(members)
            for m in members:
                if m is survivor:
                    continue
                sim = (
                    cosine_similarity(survivor.embedding, m.embedding)
                    if survivor.embedding and m.embedding
                    else 0.0
                )
                pairs.append(
                    DuplicatePair(
                        survivor_id=survivor.id,
                        duplicate_id=m.id,
                        similarity=sim,
                    )
                )
        return pairs

    # --- Consolidation (mutating) ----------------------------------------

    def consolidate_memories(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        limit: int = 100,
        offset: int = 0,
    ) -> ConsolidationResult:
        """Detect and merge duplicate memories within this tenant.

        For each connected group of similar memories, the earliest-created
        memory is kept as the survivor; all others are merged into it (highest
        importance preserved, metadata merged) and then **deleted** -- the row
        count only ever decreases, so consolidation never creates duplicates.

        Returns:
            A ``ConsolidationResult`` describing what happened.
        """
        memories = self._lts.list_memories(limit=limit, offset=offset)
        groups, comparisons = self._find_groups(memories, similarity_threshold)

        detected_pairs = 0
        merged_count = 0

        for idxs in groups:
            if len(idxs) < 2:
                continue
            members = [memories[i] for i in idxs]
            survivor = self._pick_survivor(members)

            # Preserve the highest importance across the entire group, and merge
            # metadata (survivor keys win conflicts; duplicate-only keys kept).
            max_importance = max((m.importance or 0) for m in members)
            merged_meta: Dict[str, Any] = dict(survivor.meta or {})
            duplicates = [m for m in members if m is not survivor]
            for dup in duplicates:
                detected_pairs += 1
                if dup.meta:
                    for k, v in dup.meta.items():
                        merged_meta.setdefault(k, v)

            # Update the survivor with the preserved importance + merged metadata
            # (content unchanged -> embedding left as-is; updated_at bumps via
            # SQLAlchemy onupdate, created_at untouched).
            self._lts.update_memory(
                survivor.id, importance=max_importance, metadata=merged_meta
            )

            # Remove the duplicate rows. They are deleted, never re-created.
            for dup in duplicates:
                if self._lts.delete_memory(dup.id):
                    merged_count += 1

        remaining = self._lts.count()
        logger.info(
            "memory_consolidation_complete",
            organization_id=str(self.organization_id),
            detected_pairs=detected_pairs,
            merged_count=merged_count,
            remaining_count=remaining,
        )
        return ConsolidationResult(
            detected_pairs=detected_pairs,
            merged_count=merged_count,
            comparisons=comparisons,
            remaining_count=remaining,
        )

    # --- Internals -------------------------------------------------------

    def _find_groups(self, memories: List, threshold: float):
        """Cluster memories into duplicate groups via union-find.

        Returns ``(groups, comparisons)`` where ``groups`` is a list of index
        lists (each a connected component above ``threshold``) and ``comparisons``
        is the number of pairwise cosine comparisons performed.
        """
        n = len(memories)
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        comparisons = 0
        for i in range(n):
            ei = memories[i].embedding
            if not ei:
                continue
            for j in range(i + 1, n):
                ej = memories[j].embedding
                if not ej:
                    continue
                comparisons += 1
                if cosine_similarity(ei, ej) >= threshold:
                    union(i, j)

        buckets: Dict[int, List[int]] = {}
        for i in range(n):
            buckets.setdefault(find(i), []).append(i)
        return list(buckets.values()), comparisons

    @staticmethod
    def _pick_survivor(members: List) -> Any:
        """The earliest-created memory is the survivor (preserves its identity)."""
        return min(members, key=lambda m: m.created_at or datetime.min)


__all__ = [
    "MemoryConsolidationService",
    "DuplicatePair",
    "ConsolidationResult",
    "DEFAULT_SIMILARITY_THRESHOLD",
]
