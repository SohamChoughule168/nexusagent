from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from enum import Enum


class ProviderType(str, Enum):
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class GenerationResponse:
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    cost_usd: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class StreamChunk:
    delta_content: str = ""
    delta_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None
    token_usage: Optional[TokenUsage] = None
    model: Optional[str] = None


@dataclass
class GenerationRequest:
    messages: List[Message]
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    stream: bool = False
    json_mode: bool = False
    response_schema: Optional[Dict[str, Any]] = None
    timeout: float = 60.0


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type."""
        pass

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a response from the LLM."""
        pass

    @abstractmethod
    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamChunk, None]:
        """Stream a response from the LLM."""
        pass

    @abstractmethod
    def supports_tools(self) -> bool:
        """Return whether the provider supports tool calling."""
        pass

    @abstractmethod
    def supports_json_mode(self) -> bool:
        """Return whether the provider supports JSON mode."""
        pass

    @abstractmethod
    def get_max_context_window(self, model: str) -> int:
        """Return the maximum context window for the model."""
        pass

    @abstractmethod
    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        """Calculate the cost of a generation in USD."""
        pass

    def normalize_model_name(self, model: str) -> str:
        """Normalize model name for the provider."""
        return model

    async def close(self):
        """Close any open connections."""
        pass


class ProviderError(Exception):
    """Custom exception for provider errors."""
    def __init__(self, message: str, provider: str, status_code: Optional[int] = None, retryable: bool = False):
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


class RateLimitError(ProviderError):
    """Exception for rate limit errors."""
    def __init__(self, message: str, provider: str, retry_after: Optional[float] = None):
        super().__init__(message, provider, status_code=429, retryable=True)
        self.retry_after = retry_after


class ContextLengthError(ProviderError):
    """Exception for context length errors."""
    def __init__(self, message: str, provider: str):
        super().__init__(message, provider, status_code=400, retryable=False)


class AuthenticationError(ProviderError):
    """Exception for authentication errors."""
    def __init__(self, message: str, provider: str):
        super().__init__(message, provider, status_code=401, retryable=False)


class ModelNotFoundError(ProviderError):
    """Exception for model not found errors."""
    def __init__(self, message: str, provider: str):
        super().__init__(message, provider, status_code=404, retryable=False)