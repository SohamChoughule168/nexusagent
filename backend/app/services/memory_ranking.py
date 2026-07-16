"""Memory Ranking engine (Milestone 5, Phase 2.5).

Ranks long-term memories with a *configurable weighted score* that combines:

* **semantic similarity** -- cosine similarity of the query to each memory's
  stored ``embedding`` (reuses the exact vectors + ``cosine_similarity`` from
  Phase 2.3 semantic retrieval, so the ranking stays consistent with how
  memories were embedded at write time -- **no new vector database**).
* **importance** -- the ``Memory.importance`` column that Phase 2.2 reserved and
  Phase 2.4 populated during consolidation. Normalized by a configurable max.
* **recency** -- exponential time-decay of ``Memory.created_at`` against a
  configurable half-life.

Design / reuse (no duplication of completed components):

* **RepositoryFactory / TenantAwareRepository** -- when the engine fetches its
  own candidates (``memories=None``), it lists them tenant-scoped through
  ``RepositoryFactory.memories()``, so ranking inherits the *exact* same
  ``organization_id`` isolation as the CRUD / semantic / consolidation paths.
  Tenant isolation is reused, never re-implemented.
* **LocalDeterministicEmbedder + cosine_similarity** -- the same provider Phase
  2.2 used to write ``Memory.embedding`` and Phase 2.3 used to score it. Keeping
  the read-time model identical to the write-time model means weights are
  meaningful and comparable to the semantic-retrieval scores.
* **Cosine scores are clamped to [0, 1]** for the ranking signal (negative
  cosine is "opposite", not "negative relevance"), matching the intuitive
  direction of the importance/recency signals.
* **No new vector database / no new storage** -- the engine is a *pure read +
  score* layer over the existing ``embedding`` / ``importance`` / ``created_at``
  columns. It never creates, mutates, or deletes memories, and it never touches
  the Conversation Memory service, so it cannot regress existing storage or
  short-term-memory logic.

The engine is intentionally decoupled from ``LongTermMemoryService`` so any
consumer can use it directly (reusable without touching storage):

* **Chat** (``conversations`` endpoint) -- reorder recalled memories before
  prompt injection.
* **Agent Orchestrator** -- rank durable facts/preferences mid-plan.
* **Multi-Agent Router** -- ground routing decisions in long-term memory context.
* **Future Function Calling** -- ground tool selection in long-term memory.

``LongTermMemoryService`` also exposes thin ``rank_memories`` /
``rank_memories_scored`` wrappers so existing holders of that service get
ranking for free, reusing the service's own embedder instance (keeping
write/read vector models identical).

The weighting is fully configurable via ``RankingWeights`` / ``RankingConfig``
(passed to the engine or per call), so consumers can emphasize semantic match,
importance, or recency depending on the task.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.models.all_models import Memory
from app.repositories.tenant_repository import RepositoryFactory
from app.services.embeddings import LocalDeterministicEmbedder, cosine_similarity

# --- Defaults (every value is overridable via RankingConfig/RankingWeights) ---

DEFAULT_SEMANTIC_WEIGHT = 1.0
DEFAULT_IMPORTANCE_WEIGHT = 1.0
DEFAULT_RECENCY_WEIGHT = 1.0
# Perspective scale for the `importance` column (clamped so importance / max in
# [0, 1]). The reservation comment in the Memory model implies a bounded scale;
# 10 is a sensible default matching the 0..9 values used in consolidation tests.
DEFAULT_IMPORTANCE_MAX = 10.0
# Exponential-decay half-life for recency. 30 days => a 30-day-old memory scores
# ~0.5 on recency, a 60-day-old ~0.25, etc.
DEFAULT_RECENCY_HALF_LIFE_DAYS = 30.0

_SECONDS_PER_DAY = 86400.0


@dataclass
class RankingWeights:
    """Relative weights for the three ranking signals.

    Weights need not sum to 1; the engine normalizes the final score by the
    total weight so the combined score always lands in [0, 1]. Set a weight to
    0 to disable a signal (e.g. ``semantic=0`` ranks purely by importance +
    recency), or ``importance=0`` to rank purely by semantic + recency.
    """

    semantic: float = DEFAULT_SEMANTIC_WEIGHT
    importance: float = DEFAULT_IMPORTANCE_WEIGHT
    recency: float = DEFAULT_RECENCY_WEIGHT

    @property
    def total(self) -> float:
        return self.semantic + self.importance + self.recency


@dataclass
class RankingConfig:
    """Tunable parameters for the ranking engine."""

    weights: RankingWeights = field(default_factory=RankingWeights)
    # Importance values at/above this map to a recency=1.0 (fully important).
    importance_max: float = DEFAULT_IMPORTANCE_MAX
    # Recency half-life in days for the exponential time-decay of created_at.
    recency_half_life_days: float = DEFAULT_RECENCY_HALF_LIFE_DAYS


@dataclass
class RankedMemory:
    """A memory plus its decomposed ranking scores (all in [0, 1])."""

    memory: Memory
    score: float  # total weighted (weight-normalized) score in [0, 1]
    semantic_score: float
    importance_score: float
    recency_score: float

    @property
    def components(self) -> dict:
        """Decomposed scores, useful for introspection / explainability."""
        return {
            "semantic": self.semantic_score,
            "importance": self.importance_score,
            "recency": self.recency_score,
        }


def _to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to timezone-aware UTC (tolerate naive DB timestamps)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class MemoryRanker:
    """Tenant-scoped weighted ranking over long-term memories.

    Pure read + score layer: it never creates, mutates, or deletes memories and
    never touches the Conversation Memory service, so it cannot regress
    existing storage or short-term-memory logic.
    """

    def __init__(
        self,
        db_session,
        organization_id,
        embedder=None,
        config: Optional[RankingConfig] = None,
    ):
        """Initialize with a DB session, the owning organization, and options.

        Args:
            db_session: SQLAlchemy database session.
            organization_id: UUID of the organization (tenant key). When the
                engine fetches its own candidates it uses ``RepositoryFactory``
                so candidates are always tenant-scoped.
            embedder: Optional embedder for the query vector. Defaults to the
                offline deterministic local embedder so it matches the model
                Phase 2.2 used to write ``Memory.embedding``.
            config: Optional ``RankingConfig`` with weights + scaling knobs. A
                per-call ``config`` overrides this default on ``rank``.
        """
        self.db = db_session
        self.organization_id = organization_id
        self.repository_factory = RepositoryFactory(db_session, organization_id)
        # Reuse the deterministic local embedder (matches the writer's model so
        # cosine scores are comparable to the stored vectors).
        self._embedder = embedder or LocalDeterministicEmbedder()
        self.config = config or RankingConfig()

    # --- Scoring internals ------------------------------------------------

    def _semantic_vector(self, query: Optional[str]):
        """Embed the query, or None when the query is blank (no semantic signal)."""
        if not query or not query.strip():
            return None
        return self._embedder.embed([query])[0]

    def _score_memory(
        self,
        memory: Memory,
        query_vec,
        now: datetime,
        weights: RankingWeights,
        importance_max: float,
        half_life_days: float,
    ) -> RankedMemory:
        """Compute the decomposed + weighted score for a single memory."""
        # 1) Semantic similarity: clamp cosine to [0, 1] (negative => 0 relevance).
        if query_vec is not None and getattr(memory, "embedding", None):
            semantic = max(0.0, cosine_similarity(query_vec, memory.embedding))
        else:
            semantic = 0.0

        # 2) Importance: normalized by importance_max, clamped to [0, 1].
        imp = memory.importance or 0
        if importance_max and importance_max > 0:
            importance = min(1.0, max(0.0, imp / importance_max))
        else:
            importance = 1.0 if imp > 0 else 0.0

        # 3) Recency: exponential decay of age against the half-life.
        created = _to_aware_utc(getattr(memory, "created_at", None))
        if created is None:
            recency = 1.0  # no timestamp => treat as freshest (no penalty)
        else:
            age_seconds = max(0.0, (_to_aware_utc(now) - created).total_seconds())
            half_life_seconds = half_life_days * _SECONDS_PER_DAY
            if half_life_seconds <= 0:
                recency = 1.0 if age_seconds <= 1e-9 else 0.0
            else:
                recency = math.exp(-age_seconds / half_life_seconds)

        # Weighted combination, normalized by total weight so the result lives
        # in [0, 1] regardless of the weight magnitudes chosen by the caller.
        total_w = weights.total
        if total_w <= 0:
            score = 0.0
        else:
            score = (
                weights.semantic * semantic
                + weights.importance * importance
                + weights.recency * recency
            ) / total_w

        return RankedMemory(
            memory=memory,
            score=score,
            semantic_score=semantic,
            importance_score=importance,
            recency_score=recency,
        )

    # --- Public ranking API ----------------------------------------------

    def rank(
        self,
        query: Optional[str] = None,
        memories: Optional[List[Memory]] = None,
        top_k: Optional[int] = None,
        now: Optional[datetime] = None,
        config: Optional[RankingConfig] = None,
        category: Optional[str] = None,
        agent_id=None,
    ) -> List[RankedMemory]:
        """Return memories ranked by the configured weighted score.

        Candidates are fetched tenant-scoped via ``RepositoryFactory`` when
        ``memories`` is not supplied (preserving isolation). Each memory is
        scored on semantic / importance / recency, sorted descending by total
        score (most-recent wins ties), and optionally truncated to ``top_k``.

        Args:
            query: Free-text query for the semantic signal. Optional -- when
                blank/absent the semantic component is 0 for every candidate and
                ranking falls back to importance + recency.
            memories: Explicit candidate list (e.g. results already recalled by
                semantic retrieval). If ``None``, candidates are listed from this
                tenant's repository. Callers that pass a list are responsible for
                tenant scoping upstream; the engine still never escapes its org.
            top_k: Optional cap on the number of returned memories.
            now: Reference "now" for recency decay. Defaults to the current UTC
                time; injectable so callers/tests control the recency signal.
            config: Optional per-call ``RankingConfig`` overriding the engine's
                default (lets one call re-weight without mutating the engine).
            category: Optional category filter applied when fetching candidates.
            agent_id: Optional agent scoping applied when fetching candidates.

        Returns:
            List of ``RankedMemory`` (descending score). Empty when there are no
            candidates or the explicit list is empty.
        """
        cfg = config or self.config
        weights = cfg.weights
        effective_now = now or datetime.now(timezone.utc)

        if memories is None:
            memories = self.repository_factory.memories().list_memories(
                category=category
            )
            if agent_id is not None:
                memories = [m for m in memories if m.agent_id == agent_id]

        if not memories:
            return []

        query_vec = self._semantic_vector(query)
        ranked = [
            self._score_memory(
                m, query_vec, effective_now, weights,
                cfg.importance_max, cfg.recency_half_life_days,
            )
            for m in memories
        ]
        # Descending by total score; ties broken by recency then id for stable,
        # deterministic ordering.
        ranked.sort(
            key=lambda r: (
                r.score,
                r.recency_score,
                str(r.memory.id) if r.memory.id is not None else "",
            ),
            reverse=True,
        )
        if top_k is not None:
            ranked = ranked[:top_k]
        return ranked

    def rank_memories(
        self,
        query: Optional[str] = None,
        memories: Optional[List[Memory]] = None,
        top_k: Optional[int] = None,
        now: Optional[datetime] = None,
        config: Optional[RankingConfig] = None,
        category: Optional[str] = None,
        agent_id=None,
    ) -> List[Memory]:
        """Convenience: return only the ranked ``Memory`` objects (no scores)."""
        return [
            r.memory
            for r in self.rank(
                query, memories, top_k, now, config, category, agent_id
            )
        ]

    def format_for_prompt(
        self,
        ranked: List[RankedMemory],
        max_chars: int = 4000,
    ) -> str:
        """Render ranked memories as a single prompt context block.

        Reused by Chat / Orchestrator / Router to inject recalled durable memory
        into a generation prompt, in ranking order. Empty input yields '' so
        callers can skip injection when there is nothing to recall.
        """
        if not ranked:
            return ""
        parts: List[str] = []
        total = 0
        for i, r in enumerate(ranked, start=1):
            m = r.memory
            snippet = (m.content or "")[:max_chars]
            # Always emit at least the first memory even if it alone is huge.
            if total + len(snippet) > max_chars and parts:
                break
            total += len(snippet)
            label = f"[{m.category}] " if m.category else ""
            parts.append(f"Memory {i}: {label}{snippet}")
        return "\n".join(parts)


# Convenience factory for dependency injection
def get_memory_ranker(db_session, organization_id, config=None) -> MemoryRanker:
    """Factory function to create a tenant-scoped MemoryRanker instance."""
    return MemoryRanker(db_session, organization_id, config=config)


__all__ = [
    "MemoryRanker",
    "RankedMemory",
    "RankingWeights",
    "RankingConfig",
    "get_memory_ranker",
]
