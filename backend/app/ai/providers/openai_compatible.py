"""Shared OpenAI-compatible chat-completions provider base.

OpenRouter, OpenAI, Azure OpenAI, and (via its ``/v1`` shim) Ollama all speak
the OpenAI ``/chat/completions`` wire format. This module factors the payload
building, response/stream parsing, error mapping, and cost logic into one
``OpenAICompatibleProvider`` so each concrete backend only supplies its
default base URL, auth headers, and pricing tables.
"""
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.ai.providers.base import (
    BaseLLMProvider,
    ProviderType,
    GenerationRequest,
    GenerationResponse,
    StreamChunk,
    TokenUsage,
    ProviderError,
    RateLimitError,
    ContextLengthError,
    AuthenticationError,
    ModelNotFoundError,
)


class OpenAICompatibleProvider(BaseLLMProvider):
    """Base class for any backend that implements the OpenAI chat API."""

    # Subclasses override these.
    MODEL_CONTEXT_WINDOWS: Dict[str, int] = {}
    MODEL_PRICING: Dict[str, tuple] = {}  # model -> (input $/1M, output $/1M)
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL: str = "gpt-4o-mini"
    DEFAULT_TIMEOUT = 120.0

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        super().__init__(api_key, base_url or self.DEFAULT_BASE_URL)
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Content-Type": "application/json",
                **self._auth_headers(),
                **(default_headers or {}),
            },
            timeout=httpx.Timeout(timeout),
        )

    # -- hooks subclasses may override ----------------------------------- #
    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _chat_completions_path(self) -> str:
        """Relative path (off ``base_url``) for the chat completions call."""
        return "/chat/completions"

    def _api_key_for_cost(self) -> Optional[str]:
        return self.api_key

    # -- interface ------------------------------------------------------ #
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        payload = self._build_payload(request, stream=False)
        try:
            response = await self.client.post(self._chat_completions_path(), json=payload)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data, request.model)
        except httpx.HTTPStatusError as e:
            await self._handle_error(e, request.model)
        except httpx.TimeoutException:
            raise ProviderError(
                "Request timed out", self.provider_type.value,
                status_code=408, retryable=True,
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError(
                f"Unexpected error: {str(e)}", self.provider_type.value,
                retryable=True,
            )

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamChunk, None]:
        payload = self._build_payload(request, stream=True)
        try:
            async with self.client.stream(
                "POST", self._chat_completions_path(), json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        chunk_data = json.loads(line[6:])
                        chunk = self._parse_stream_chunk(chunk_data, request.model)
                        if chunk:
                            yield chunk
        except httpx.HTTPStatusError as e:
            await self._handle_error(e, request.model)
        except httpx.TimeoutException:
            raise ProviderError(
                "Stream timed out", self.provider_type.value,
                status_code=408, retryable=True,
            )
        except Exception as e:  # noqa: BLE001
            raise ProviderError(
                f"Stream error: {str(e)}", self.provider_type.value,
                retryable=True,
            )

    def _build_payload(self, request: GenerationRequest, stream: bool) -> Dict[str, Any]:
        messages = []
        for msg in request.messages:
            message_dict: Dict[str, Any] = {
                "role": msg.role.value,
                "content": msg.content,
            }
            if msg.name:
                message_dict["name"] = msg.name
            if msg.tool_call_id:
                message_dict["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                message_dict["tool_calls"] = msg.tool_calls
            messages.append(message_dict)

        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": stream,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            payload["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            payload["presence_penalty"] = request.presence_penalty
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if request.tools:
            payload["tools"] = request.tools
            if request.tool_choice:
                payload["tool_choice"] = request.tool_choice
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if request.response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": request.response_schema,
                    "strict": True,
                },
            }
        return payload

    def _parse_response(self, data: Dict[str, Any], model: str) -> GenerationResponse:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""
        tool_calls = message.get("tool_calls", [])
        usage_data = data.get("usage", {}) or {}
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        return GenerationResponse(
            content=content,
            tool_calls=tool_calls,
            token_usage=usage,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model", model),
            cost_usd=self.calculate_cost(model, usage),
            raw_response=data,
        )

    def _parse_stream_chunk(self, data: Dict[str, Any], model: str) -> Optional[StreamChunk]:
        choices = data.get("choices", [])
        if not choices:
            return None
        choice = choices[0]
        delta = choice.get("delta", {})
        delta_content = delta.get("content", "")
        delta_tool_calls = delta.get("tool_calls", [])
        if not delta_content and not delta_tool_calls:
            usage_data = data.get("usage")
            if usage_data:
                usage = TokenUsage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
                return StreamChunk(
                    token_usage=usage,
                    finish_reason=choice.get("finish_reason"),
                    model=data.get("model", model),
                )
            return None
        return StreamChunk(
            delta_content=delta_content,
            delta_tool_calls=delta_tool_calls,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model", model),
        )

    def supports_tools(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return True

    def get_max_context_window(self, model: str) -> int:
        return self.MODEL_CONTEXT_WINDOWS.get(model, 128000)

    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        pricing = self.MODEL_PRICING.get(model)
        if not pricing:
            return 0.0
        input_price, output_price = pricing
        input_cost = (usage.prompt_tokens / 1_000_000) * input_price
        output_cost = (usage.completion_tokens / 1_000_000) * output_price
        return input_cost + output_cost

    async def _handle_error(self, error: httpx.HTTPStatusError, model: str):
        status_code = error.response.status_code
        try:
            error_data = error.response.json()
            error_message = error_data.get("error", {}).get("message", str(error))
        except Exception:  # noqa: BLE001
            error_message = str(error)
        if status_code == 401:
            raise AuthenticationError(error_message, self.provider_type.value)
        elif status_code == 404:
            raise ModelNotFoundError(error_message, self.provider_type.value)
        elif status_code == 429:
            retry_after = None
            try:
                retry_after = float(error.response.headers.get("Retry-After", 0))
            except (ValueError, TypeError):
                pass
            raise RateLimitError(error_message, self.provider_type.value, retry_after=retry_after)
        elif status_code == 400 and "context" in error_message.lower():
            raise ContextLengthError(error_message, self.provider_type.value)
        else:
            raise ProviderError(
                error_message, self.provider_type.value,
                status_code=status_code, retryable=status_code >= 500,
            )

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class OpenAIProvider(OpenAICompatibleProvider):
    """First-party OpenAI chat provider (OpenAI-compatible wire format)."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    MODEL_CONTEXT_WINDOWS = {
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4-turbo": 128000,
        "gpt-3.5-turbo": 16385,
    }
    MODEL_PRICING = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50),
    }

    @property
    def provider_type(self):
        return ProviderType.OPENAI

