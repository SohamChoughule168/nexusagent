"""Conversation Memory service (Milestone 5, Phase 1).

Provides conversation history retrieval, context window management,
automatic history injection, and token budgeting for chat and orchestration
pipelines. Integrates with existing architecture without duplicating services:

* **RepositoryFactory** -- tenant-scoped repository access for Conversation
  and Message models (inherits tenant isolation)
* **Conversation API** -- reuses existing conversation/message persistence
* **Multi-Agent Router** -- conversation context available for routing decisions
* **Agent Orchestrator** -- conversation memory available for agent-to-agent communication
* **Function Calling** -- conversation history can inform tool selection
* **Tool Execution Engine** -- execution context enriched with conversation history
* **RAG Pipeline** -- conversation history combined with retrieved chunks
* **TenantContext** -- organization-scoped conversation memory
* **RBAC** -- access controlled via existing authentication/authorization

The service enables:
1. Conversation history retrieval (get recent messages for a conversation)
2. Context window management (limit messages to fit within token budget)
3. Automatic history injection (prepend conversation history to LLM prompts)
4. Token budgeting (estimate and limit tokens for context)
"""

from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from app.core.logging import get_logger
from app.models.all_models import Conversation, Message
from app.repositories.tenant_repository import RepositoryFactory

# ``tiktoken`` gives exact token counts for OpenAI-family models but is an
# optional dependency: when it is not installed we fall back to a deterministic
# character-based heuristic so token budgeting still works fully offline (the
# same optional-import pattern used elsewhere in the service layer, e.g. the PDF
# parsers in ``app.services.ingestion``).
try:  # pragma: no cover - exercised implicitly by whichever branch is active
    import tiktoken  # type: ignore

    _TIKTOKEN_AVAILABLE = True
except ImportError:  # pragma: no cover
    tiktoken = None  # type: ignore
    _TIKTOKEN_AVAILABLE = False

logger = get_logger(__name__)

# Token estimation constants
# Using cl100k_base encoding (used by GPT-4, GPT-3.5-turbo, text-embedding-ada-002)
_ENCODING_NAME = "cl100k_base"
# Reserve tokens for system prompt, instructions, and response generation
_RESERVE_TOKENS = 500
# Approximate characters-per-token for the offline heuristic (English text).
_CHARS_PER_TOKEN = 4

# --- Summary engine (Milestone5, Phase2.1) --------------------------------
# Cheap, fast model used for summarization by default. Overridable per call.
_SUMMARY_DEFAULT_MODEL = "anthropic/claude-3.5-haiku"
# Fraction of the context-token budget handed to *recent* history when a summary
# already exists. The summary covers earlier turns, so the budget is spent on
# the freshest messages instead of resending old ones.
_SUMMARY_RECENT_WINDOW_RATIO = 0.6
# Default thresholds that trigger (re)summarization of a conversation.
_SUMMARY_DEFAULT_MESSAGE_THRESHOLD = 20
_SUMMARY_DEFAULT_TOKEN_THRESHOLD = 2000

_SUMMARY_SYSTEM_PROMPT = (
    "You are a conversation summarizer. Produce a concise, factual summary of "
    "the conversation so far. Preserve key facts, the user's intent, any "
    "decisions made, and any open questions. Do not invent details that were "
    "not stated."
)


class ConversationMemoryService:
    """Service for managing conversation memory and context."""

    def __init__(self, db_session, organization_id: UUID):
        """Initialize with database session and organization ID for tenant isolation.

        Args:
            db_session: SQLAlchemy database session
            organization_id: UUID of the organization for tenant scoping
        """
        self.db = db_session
        self.organization_id = organization_id
        self.repository_factory = RepositoryFactory(db_session, organization_id)
        try:
            self.encoding = tiktoken.get_encoding(_ENCODING_NAME)
        except Exception:
            # Fallback to a simple estimation if tiktoken is not available
            self.encoding = None
            logger.warning("tiktoken not available, using approximate token counting")

    def get_conversation_history(
        self,
        conversation_id: UUID,
        limit: int = 50
    ) -> List[Message]:
        """Retrieve conversation history for a conversation.

        Args:
            conversation_id: UUID of the conversation
            limit: Maximum number of messages to retrieve (most recent first)

        Returns:
            List of Message objects ordered chronologically (oldest first)
        """
        # Verify conversation exists and belongs to organization
        conversation_repo = self.repository_factory.conversations()
        conversation = conversation_repo.get(conversation_id)
        if conversation is None:
            logger.warning(
                "conversation_not_found_or_access_denied",
                conversation_id=str(conversation_id),
                organization_id=str(self.organization_id)
            )
            return []

        # Get messages (most recent first from repository)
        message_repo = self.repository_factory.messages()
        recent_messages = message_repo.get_by_conversation(conversation_id, limit=limit)

        # Return in chronological order (oldest first) for proper conversation flow
        return list(reversed(recent_messages))

    def estimate_token_count(self, text: str) -> int:
        """Estimate token count for a text string.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated number of tokens
        """
        if self.encoding:
            return len(self.encoding.encode(text))
        else:
            # Rough approximation: 1 token ≈ 4 characters for English text
            return len(text) // 4

    def estimate_messages_token_count(self, messages: List[Message]) -> int:
        """Estimate total token count for a list of messages.

        Args:
            messages: List of Message objects

        Returns:
            Estimated total token count
        """
        total = 0
        for message in messages:
            # Add tokens for role formatting and content
            total += self.estimate_token_count(f"{message.role}: {message.content}")
            # Add overhead for message structure (approximately 3 tokens per message)
            total += 3
        return total

    def truncate_history_to_token_limit(
        self,
        messages: List[Message],
        max_tokens: int
    ) -> List[Message]:
        """Truncate conversation history to fit within token limit.

        Prioritizes recent messages (keep most recent) when truncating.

        Args:
            messages: List of Message objects (chronological order)
            max_tokens: Maximum tokens allowed for the history

        Returns:
            Truncated list of messages that fits within token limit
        """
        if not messages:
            return messages

        # Start from the most recent messages and work backwards
        truncated = []
        current_tokens = 0

        # Process messages in reverse order (most recent first)
        for message in reversed(messages):
            message_tokens = self.estimate_token_count(
                f"{message.role}: {message.content}"
            ) + 3  # message overhead

            if current_tokens + message_tokens > max_tokens:
                # Stop adding messages when we'd exceed the limit
                break

            truncated.insert(0, message)  # Insert at beginning to maintain order
            current_tokens += message_tokens

        logger.debug(
            "conversation_history_truncated",
            original_count=len(messages),
            truncated_count=len(truncated),
            original_tokens=self.estimate_messages_token_count(messages),
            truncated_tokens=current_tokens,
            max_tokens=max_tokens
        )

        return truncated

    def get_context_window_messages(
        self,
        conversation_id: UUID,
        max_context_tokens: int = 2000
    ) -> List[Message]:
        """Get conversation messages that fit within context window.

        Args:
            conversation_id: UUID of the conversation
            max_context_tokens: Maximum tokens to allocate for conversation history

        Returns:
            List of Message objects that fit within the context window
        """
        # Get more messages than we might need to allow for proper truncation
        raw_messages = self.get_conversation_history(conversation_id, limit=100)

        # Reserve tokens for system prompt, user query, and response
        available_tokens = max_context_tokens - _RESERVE_TOKENS
        if available_tokens < 100:  # Minimum reasonable token allocation
            available_tokens = 100

        # Truncate to fit within available tokens
        return self.truncate_history_to_token_limit(raw_messages, available_tokens)

    def format_messages_for_prompt(self, messages: List[Message]) -> str:
        """Format conversation messages for inclusion in LLM prompt.

        Args:
            messages: List of Message objects (chronological order)

        Returns:
            Formatted string suitable for prepending to LLM prompts
        """
        if not messages:
            return ""

        formatted_lines = []
        for message in messages:
            # Format as: role: content
            formatted_lines.append(f"{message.role}: {message.content}")

        return "\n".join(formatted_lines)

    def inject_conversation_history(
        self,
        conversation_id: UUID,
        user_query: str,
        max_context_tokens: int = 2000
    ) -> Tuple[str, List[Message]]:
        """Inject conversation history into a user query for LLM consumption.

        Args:
            conversation_id: UUID of the conversation
            user_query: The user's current query/message
            max_context_tokens: Maximum tokens for conversation history context

        Returns:
            Tuple of (enhanced_prompt, history_messages) where:
            - enhanced_prompt: User query with conversation history prepended
            - history_messages: The conversation history messages that were used
        """
        # Get conversation history that fits within context window
        history_messages = self.get_context_window_messages(
            conversation_id, max_context_tokens
        )

        # Format history for prompt
        history_text = self.format_messages_for_prompt(history_messages)

        # Construct enhanced prompt
        if history_text:
            enhanced_prompt = (
                f"Previous conversation:\n{history_text}\n\n"
                f"Current query: {user_query}"
            )
        else:
            enhanced_prompt = user_query

        logger.debug(
            "conversation_history_injected",
            conversation_id=str(conversation_id),
            history_message_count=len(history_messages),
            history_tokens=self.estimate_messages_token_count(history_messages),
            query_tokens=self.estimate_token_count(user_query),
            total_prompt_tokens=self.estimate_token_count(enhanced_prompt)
        )

        return enhanced_prompt, history_messages

    def get_conversation_summary(self, conversation_id: UUID) -> Optional[str]:
        """Get or generate a summary of the conversation.

        Args:
            conversation_id: UUID of the conversation

        Returns:
            Conversation summary if available, None otherwise
        """
        conversation_repo = self.repository_factory.conversations()
        conversation = conversation_repo.get(conversation_id)
        if conversation:
            return conversation.summary
        return None

    def update_conversation_summary(self, conversation_id: UUID, summary: str) -> bool:
        """Update the conversation summary.

        Args:
            conversation_id: UUID of the conversation
            summary: Summary text to store

        Returns:
            True if successful, False otherwise
        """
        conversation_repo = self.repository_factory.conversations()
        conversation = conversation_repo.get(conversation_id)
        if conversation:
            conversation.summary = summary
            conversation_repo.update(conversation)
            logger.info(
                "conversation_summary_updated",
                conversation_id=str(conversation_id),
                summary_length=len(summary)
            )
            return True
        return False

    # --- Conversation Summary Engine (Milestone5, Phase2.1) -----------
    #
    # Reuses the existing ``Conversation.summary`` field and the tenant-scoped
    # ``RepositoryFactory`` (inherited tenant isolation). Generation calls the
    # existing ``OpenRouterProvider`` (mirrors ``app.services.rag``), falling
    # back gracefully when no LLM is configured so offline/test paths are
    # unaffected.

    def should_summarize(
        self,
        conversation_id: UUID,
        message_threshold: int = _SUMMARY_DEFAULT_MESSAGE_THRESHOLD,
        token_threshold: int = _SUMMARY_DEFAULT_TOKEN_THRESHOLD,
    ) -> bool:
        """Decide whether a conversation has crossed a summarization threshold.

        A conversation is summarized when EITHER its persisted message count OR
        its estimated history token count exceeds the configured threshold. The
        message count is read from ``Conversation.message_count`` (kept accurate
        by the chat/orchestration pipelines); when it is unavailable the history
        is counted directly as a fallback.

        Args:
            conversation_id: UUID of the conversation.
            message_threshold: Summarize once message count exceeds this.
            token_threshold: Summarize once estimated history tokens exceed this.

        Returns:
            True if a (re)summarization should be triggered.
        """
        conversation_repo = self.repository_factory.conversations()
        conversation = conversation_repo.get(conversation_id)
        if conversation is None:
            return False

        # Prefer the persisted counter (cheap, index-friendly).
        msg_count = conversation.message_count or 0
        if msg_count >= message_threshold:
            return True

        # Fallback: estimate tokens from the actual history.
        history = self.get_conversation_history(conversation_id, limit=100)
        if not history:
            return False
        return self.estimate_messages_token_count(history) >= token_threshold

    def _build_summary_user_prompt(
        self, existing_summary: Optional[str], history_text: str
    ) -> str:
        """Build the user prompt for the summarizer LLM.

        When an existing summary is present it is passed back so the LLM
        *extends* the summary (iterative summarization) rather than restarting
        from scratch.
        """
        if existing_summary:
            return (
                "Here is the existing summary of the conversation:\n"
                f"{existing_summary}\n\n"
                "Here are the more recent messages:\n"
                f"{history_text}\n\n"
                "Update the summary to incorporate the new messages. "
                "Return only the updated summary."
            )
        return (
            "Summarize the following conversation concisely. "
            "Return only the summary.\n\n"
            f"{history_text}"
        )

    async def generate_summary(
        self,
        conversation_id: UUID,
        model: Optional[str] = None,
        provider: Optional["_LLMProviderBase"] = None,
    ) -> Optional[str]:
        """Generate (and persist) a summary of the conversation using the LLM.

        Uses the conversation's existing ``summary`` as the base when present, so
        the summary is *extended* rather than regenerated from scratch
        (iterative summarization). The result is persisted via
        :meth:`update_conversation_summary`.

        Tenant isolation is inherited from the service (``RepositoryFactory``).

        Args:
            conversation_id: UUID of the conversation to summarize.
            model: Optional model override (defaults to a cheap, fast model).
            provider: Optional pre-constructed LLM provider (used by tests and
                callers that already hold one). When ``None``, a provider is built
                from configuration; if no API key is configured the call is a safe
                no-op that returns the existing summary (if any).

        Returns:
            The generated (or existing) summary string, or ``None`` if the
            conversation does not exist or nothing could be produced.
        """
        # Local imports keep the module-level ``Message`` symbol (used here for
        # ORM objects) distinct from the provider's ``Message``.
        from app.ai.providers.base import (
            BaseLLMProvider as _LLMProviderBase,  # noqa: F401  (type hint only)
        )
        from app.ai.providers.base import (
            GenerationRequest,
            Message as ProviderMessage,
            MessageRole,
        )
        from app.ai.providers.openrouter import OpenRouterProvider
        from app.core.config import settings

        conversation_repo = self.repository_factory.conversations()
        conversation = conversation_repo.get(conversation_id)
        if conversation is None:
            logger.warning(
                "summary_generation_skipped_no_conversation",
                conversation_id=str(conversation_id),
                organization_id=str(self.organization_id),
            )
            return None

        # Gather the conversation history to summarize (most recent first -> reversed).
        history = self.get_conversation_history(conversation_id, limit=100)
        if not history:
            # Nothing to summarize yet; keep any existing summary untouched.
            return conversation.summary

        existing_summary = conversation.summary
        history_text = self.format_messages_for_prompt(history)
        user_prompt = self._build_summary_user_prompt(existing_summary, history_text)

        # Provider resolution: reuse caller-supplied provider, else build from
        # config. When unconfigured (offline/test), this is a safe no-op.
        own_provider = provider is None
        if own_provider:
            api_key = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
            if not api_key:
                logger.debug(
                    "summary_generation_skipped_no_llm",
                    conversation_id=str(conversation_id),
                )
                return existing_summary
            provider = OpenRouterProvider(
                api_key=api_key,
                base_url=settings.OPENROUTER_BASE_URL,
            )

        try:
            request = GenerationRequest(
                messages=[
                    ProviderMessage(role=MessageRole.SYSTEM, content=_SUMMARY_SYSTEM_PROMPT),
                    ProviderMessage(role=MessageRole.USER, content=user_prompt),
                ],
                model=model or _SUMMARY_DEFAULT_MODEL,
                temperature=0.0,
                max_tokens=512,
            )
            response = await provider.generate(request)
            summary = (response.content or "").strip()
            if not summary:
                return existing_summary
            self.update_conversation_summary(conversation_id, summary)
            return summary
        except Exception as exc:  # resilience: never break the caller on LLM failure
            logger.warning(
                "summary_generation_failed",
                conversation_id=str(conversation_id),
                error=str(exc),
            )
            return existing_summary
        finally:
            if own_provider and provider is not None:
                try:
                    await provider.close()
                except Exception:
                    pass

    async def maybe_generate_summary(
        self,
        conversation_id: UUID,
        message_threshold: int = _SUMMARY_DEFAULT_MESSAGE_THRESHOLD,
        token_threshold: int = _SUMMARY_DEFAULT_TOKEN_THRESHOLD,
        model: Optional[str] = None,
        provider: Optional["_LLMProviderBase"] = None,
    ) -> Optional[str]:
        """Generate a summary only after configurable thresholds are crossed.

        Wraps :meth:`should_summarize` + :meth:`generate_summary` so callers can
        fire-and-forget summarization at the end of a chat/orchestration turn
        without re-checking thresholds themselves.

        Returns:
            The generated summary, or ``None`` when thresholds were not met or
            generation was a no-op.
        """
        if not self.should_summarize(
            conversation_id,
            message_threshold=message_threshold,
            token_threshold=token_threshold,
        ):
            return None
        return await self.generate_summary(
            conversation_id, model=model, provider=provider
        )

    def build_context(
        self,
        conversation_id: UUID,
        user_query: str,
        max_context_tokens: int = 2000,
    ) -> Tuple[str, Optional[str], List[Message]]:
        """Build an LLM prompt that leads with the conversation summary.

        Order of injection (Milestone5, Phase2.1):

        1. **Summary first** -- if the conversation has a persisted ``summary``
           it is injected as a compact recap so old turns are *represented, not
           resent*.
        2. **Recent history second** -- the most recent messages (token-budgeted)
           are injected so short-term context is preserved.
        3. **RAG context** is layered on by the calling pipeline
           (``app.services.rag``), which composes the retrieved chunks into the
           final generation prompt.

        Token optimization: when a summary is present, the recent-history window
        is shrunk (the summary already covers earlier turns) so the budget is
        spent on the newest messages -- equivalent to *replacing very old messages
        with the summary* without mutating persisted data. Existing token
        budgeting is preserved.

        Returns:
            Tuple of ``(enhanced_prompt, summary_used, history_messages)``.
        """
        summary = self.get_conversation_summary(conversation_id)

        # When a summary exists, give recent history a smaller slice of the
        # budget: the summary already covers older context.
        window = max_context_tokens
        if summary:
            window = max(100, int(max_context_tokens * _SUMMARY_RECENT_WINDOW_RATIO))

        history_messages = self.get_context_window_messages(
            conversation_id, max_context_tokens=window
        )
        history_text = self.format_messages_for_prompt(history_messages)

        parts: List[str] = []
        if summary:
            parts.append(f"Conversation summary:\n{summary}")
        if history_text:
            parts.append(f"Recent conversation:\n{history_text}")
        parts.append(f"Current query: {user_query}")

        enhanced_prompt = "\n\n".join(parts)

        logger.debug(
            "summary_context_built",
            conversation_id=str(conversation_id),
            has_summary=bool(summary),
            summary_tokens=self.estimate_token_count(summary or ""),
            history_message_count=len(history_messages),
            history_tokens=self.estimate_messages_token_count(history_messages),
            query_tokens=self.estimate_token_count(user_query),
        )

        return enhanced_prompt, summary, history_messages


# Convenience function for dependency injection
def get_conversation_memory_service(db_session, organization_id: UUID) -> ConversationMemoryService:
    """Factory function to create ConversationMemoryService instance.

    Args:
        db_session: SQLAlchemy database session
        organization_id: UUID of the organization

    Returns:
        ConversationMemoryService instance
    """
    return ConversationMemoryService(db_session, organization_id)


__all__ = [
    "ConversationMemoryService",
    "get_conversation_memory_service"
]