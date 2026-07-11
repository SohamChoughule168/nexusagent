import json
import time
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx

from app.ai.providers.base import (
    BaseLLMProvider,
    ProviderType,
    Message,
    MessageRole,
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


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter LLM provider implementation."""

    # Model context windows (in tokens)
    MODEL_CONTEXT_WINDOWS = {
        "anthropic/claude-3.5-sonnet": 200000,
        "anthropic/claude-3.5-haiku": 200000,
        "anthropic/claude-3-opus": 200000,
        "openai/gpt-4o": 128000,
        "openai/gpt-4o-mini": 128000,
        "openai/gpt-4-turbo": 128000,
        "openai/gpt-3.5-turbo": 16385,
        "google/gemini-pro-1.5": 2000000,
        "google/gemini-flash-1.5": 1000000,
        "meta-llama/llama-3.1-405b": 128000,
        "meta-llama/llama-3.1-70b": 128000,
        "meta-llama/llama-3.1-8b": 128000,
    }

    # Pricing per 1M tokens (input, output) in USD
    MODEL_PRICING = {
        "anthropic/claude-3.5-sonnet": (3.00, 15.00),
        "anthropic/claude-3.5-haiku": (0.25, 1.25),
        "anthropic/claude-3-opus": (15.00, 75.00),
        "openai/gpt-4o": (2.50, 10.00),
        "openai/gpt-4o-mini": (0.15, 0.60),
        "openai/gpt-4-turbo": (10.00, 30.00),
        "openai/gpt-3.5-turbo": (0.50, 1.50),
        "google/gemini-pro-1.5": (1.25, 5.00),
        "google/gemini-flash-1.5": (0.075, 0.30),
        "meta-llama/llama-3.1-405b": (3.00, 3.00),
        "meta-llama/llama-3.1-70b": (0.90, 0.90),
        "meta-llama/llama-3.1-8b": (0.06, 0.06),
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        default_headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(api_key, base_url)
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://nexusagent.ai",
                "X-Title": "NexusAgent AI",
                **(default_headers or {}),
            },
            timeout=httpx.Timeout(120.0),
        )
        self._model_cache: Dict[str, Dict[str, Any]] = {}

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENROUTER

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a non-streaming response."""
        payload = self._build_payload(request, stream=False)

        try:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            return self._parse_response(data, request.model)

        except httpx.HTTPStatusError as e:
            await self._handle_error(e, request.model)
        except httpx.TimeoutException:
            raise ProviderError(
                "Request timed out",
                self.provider_type.value,
                status_code=408,
                retryable=True,
            )
        except Exception as e:
            raise ProviderError(
                f"Unexpected error: {str(e)}",
                self.provider_type.value,
                retryable=True,
            )

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamChunk, None]:
        """Stream a response."""
        payload = self._build_payload(request, stream=True)

        try:
            async with self.client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue

                    if line.startswith("data: "):
                        data = line[6:]
                        try:
                            chunk_data = json.loads(data)
                            chunk = self._parse_stream_chunk(chunk_data, request.model)
                            if chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue

        except httpx.HTTPStatusError as e:
            await self._handle_error(e, request.model)
        except httpx.TimeoutException:
            raise ProviderError(
                "Stream timed out",
                self.provider_type.value,
                status_code=408,
                retryable=True,
            )
        except Exception as e:
            raise ProviderError(
                f"Stream error: {str(e)}",
                self.provider_type.value,
                retryable=True,
            )

    def _build_payload(self, request: GenerationRequest, stream: bool) -> Dict[str, Any]:
        """Build the request payload for OpenRouter."""
        messages = []
        for msg in request.messages:
            message_dict = {
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

        payload = {
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
        """Parse a non-streaming response."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content", "") or ""
        tool_calls = message.get("tool_calls", [])

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        cost = self.calculate_cost(model, usage)

        return GenerationResponse(
            content=content,
            tool_calls=tool_calls,
            token_usage=usage,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model", model),
            cost_usd=cost,
            raw_response=data,
        )

    def _parse_stream_chunk(self, data: Dict[str, Any], model: str) -> Optional[StreamChunk]:
        """Parse a streaming chunk."""
        choices = data.get("choices", [])
        if not choices:
            return None

        choice = choices[0]
        delta = choice.get("delta", {})

        delta_content = delta.get("content", "")
        delta_tool_calls = delta.get("tool_calls", [])

        if not delta_content and not delta_tool_calls:
            # Could be usage info at the end
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
        """Calculate cost in USD."""
        pricing = self.MODEL_PRICING.get(model)
        if not pricing:
            return 0.0

        input_price, output_price = pricing
        input_cost = (usage.prompt_tokens / 1_000_000) * input_price
        output_cost = (usage.completion_tokens / 1_000_000) * output_price
        return input_cost + output_cost

    async def _handle_error(self, error: httpx.HTTPStatusError, model: str):
        """Handle HTTP errors from OpenRouter."""
        status_code = error.response.status_code

        try:
            error_data = error.response.json()
            error_message = error_data.get("error", {}).get("message", str(error))
        except Exception:
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
            raise RateLimitError(
                error_message,
                self.provider_type.value,
                retry_after=retry_after,
            )
        elif status_code == 400 and "context" in error_message.lower():
            raise ContextLengthError(error_message, self.provider_type.value)
        else:
            raise ProviderError(
                error_message,
                self.provider_type.value,
                status_code=status_code,
                retryable=status_code >= 500,
            )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class OpenRouterProviderWithFallback:
    """OpenRouter provider with automatic fallback to alternative models."""

    def __init__(self, primary_provider: OpenRouterProvider):
        self.primary = primary_provider

    async def generate_with_fallback(
        self,
        request: GenerationRequest,
        fallback_models: List[str] = None,
    ) -> GenerationResponse:
        """Try primary model, then fallback models on failure."""
        models_to_try = [request.model]
        if fallback_models:
            models_to_try.extend(fallback_models)

        last_error = None
        for model in models_to_try:
            try:
                request.model = model
                return await self.primary.generate(request)
            except ProviderError as e:
                last_error = e
                if not e.retryable:
                    break
                continue

        raise last_error

    async def stream_with_fallback(
        self,
        request: GenerationRequest,
        fallback_models: List[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Try streaming with fallback models."""
        models_to_try = [request.model]
        if fallback_models:
            models_to_try.extend(fallback_models)

        for model in models_to_try:
            try:
                request.model = model
                async for chunk in self.primary.stream(request):
                    yield chunk
                return  # Success
            except ProviderError as e:
                if not e.retryable:
                    raise
                continue

        raise last_error