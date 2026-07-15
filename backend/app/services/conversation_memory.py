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