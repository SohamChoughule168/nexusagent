"""Anthropic Claude provider.

Anthropic's Messages API uses a different wire format from OpenAI: a separate
``system`` parameter, ``user``/``assistant`` messages, and tool calls expressed
as ``tool_use`` / ``tool_result`` content blocks. This module implements that
mapping on top of the shared :class:`BaseLLMProvider` contract so the rest of
the app stays provider-agnostic.
"""
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.ai.providers.base import (
    BaseLLMProvider,
    ProviderType,
    Message,
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

# Friendly alias -> concrete snapshot id used by the API.
_MODEL_ALIASES = {
    "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku": "claude-3-5-haiku-20241022",
    "claude-3-opus": "claude-3-opus-20240229",
}

_MODEL_CONTEXT_WINDOWS = {
    "claude-3-5-sonnet-20241022": 200000,
    "claude-3-5-haiku-20241022": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
}

_MODEL_PRICING = {
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.25, 1.25),
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
}

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude Messages API provider."""

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        super().__init__(api_key, base_url)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(120.0),
        )

    @property
    def provider_type(self):
        return ProviderType.ANTHROPIC

    def normalize_model_name(self, model: str) -> str:
        if not model:
            return self.DEFAULT_MODEL
        return _MODEL_ALIASES.get(model, model)

    # -- request shaping ------------------------------------------------ #
    def _to_anthropic(self, request: GenerationRequest):
        model = self.normalize_model_name(request.model)
        system_parts: List[str] = []
        messages: List[Dict[str, Any]] = []

        for msg in request.messages:
            if msg.role.value == "system":
                system_parts.append(msg.content)
                continue
            messages.append(self._convert_message(msg))

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences
        if request.tools:
            payload["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"].get("parameters", {}),
                }
                for t in request.tools
            ]
            if request.tool_choice == "required":
                payload["tool_choice"] = {"type": "any"}
            elif request.tool_choice and request.tool_choice not in ("auto", "none"):
                payload["tool_choice"] = {"type": "tool", "name": request.tool_choice}
            else:
                payload["tool_choice"] = {"type": "auto"}
        return payload

    def _convert_message(self, msg: Message) -> Dict[str, Any]:
        role = msg.role.value
        if role == "tool":
            # tool_result must live inside a user message content block.
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                ],
            }
        if msg.tool_calls:
            blocks: List[Dict[str, Any]] = [{"type": "text", "text": msg.content or ""}]
            for tc in msg.tool_calls:
                fn = tc.get("function", {})
                try:
                    parsed = json.loads(fn.get("arguments", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    parsed = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id"),
                        "name": fn.get("name"),
                        "input": parsed,
                    }
                )
            return {"role": role, "content": blocks}
        return {"role": role, "content": msg.content}

    # -- response parsing ---------------------------------------------- #
    @staticmethod
    def _tool_calls_from_content(content: List[Dict[str, Any]]):
        calls = []
        for block in content:
            if block.get("type") == "tool_use":
                calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )
        return calls

    def _usage(self, data: Dict[str, Any]) -> TokenUsage:
        u = data.get("usage", {}) or {}
        return TokenUsage(
            prompt_tokens=u.get("input_tokens", 0),
            completion_tokens=u.get("output_tokens", 0),
            total_tokens=u.get("input_tokens", 0) + u.get("output_tokens", 0),
        )

    # -- interface ------------------------------------------------------ #
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        payload = self._to_anthropic(request)
        try:
            resp = await self.client.post("/messages", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            self._handle_error(e)
            return  # unreachable; _handle_error raises
        except httpx.TimeoutException:
            raise ProviderError("Request timed out", "anthropic", status_code=408, retryable=True)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Unexpected error: {str(e)}", "anthropic", retryable=True)

        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        tool_calls = self._tool_calls_from_content(content_blocks)
        usage = self._usage(data)
        return GenerationResponse(
            content=text,
            tool_calls=tool_calls,
            token_usage=usage,
            finish_reason=data.get("stop_reason"),
            model=self.normalize_model_name(request.model),
            cost_usd=self.calculate_cost(self.normalize_model_name(request.model), usage),
            raw_response=data,
        )

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamChunk, None]:
        payload = self._to_anthropic(request)
        payload["stream"] = True
        try:
            async with self.client.stream("POST", "/messages", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    for chunk in self._parse_sse_line(line, request.model):
                        yield chunk
        except httpx.HTTPStatusError as e:
            self._handle_error(e)
        except httpx.TimeoutException:
            raise ProviderError("Stream timed out", "anthropic", status_code=408, retryable=True)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Stream error: {str(e)}", "anthropic", retryable=True)

    def _parse_sse_line(self, line: str, model: str) -> List[StreamChunk]:
        if not line or not line.startswith("data: "):
            return []
        raw = line[6:].strip()
        if raw == "[DONE]":
            return []
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return []
        etype = event.get("type")
        if etype == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                return [StreamChunk(delta_content=delta.get("text", ""), model=model)]
            if delta.get("type") == "input_json_delta":
                return [
                    StreamChunk(
                        delta_tool_calls=[
                            {"id": event.get("index"), "function": {"arguments": delta.get("partial_json", "")}}
                        ],
                        model=model,
                    )
                ]
        elif etype == "message_delta":
            u = event.get("usage", {}) or {}
            if u:
                return [
                    StreamChunk(
                        token_usage=TokenUsage(
                            prompt_tokens=0,
                            completion_tokens=u.get("output_tokens", 0),
                        ),
                        finish_reason=event.get("delta", {}).get("stop_reason"),
                        model=model,
                    )
                ]
        return []

    def supports_tools(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return False

    def get_max_context_window(self, model: str) -> int:
        return _MODEL_CONTEXT_WINDOWS.get(self.normalize_model_name(model), 200000)

    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        pricing = _MODEL_PRICING.get(self.normalize_model_name(model))
        if not pricing:
            return 0.0
        in_p, out_p = pricing
        return (usage.prompt_tokens / 1_000_000) * in_p + (usage.completion_tokens / 1_000_000) * out_p

    def _handle_error(self, error: httpx.HTTPStatusError):
        status = error.response.status_code
        try:
            msg = error.response.json().get("error", {}).get("message", str(error))
        except Exception:  # noqa: BLE001
            msg = str(error)
        if status == 401:
            raise AuthenticationError(msg, "anthropic")
        if status == 404:
            raise ModelNotFoundError(msg, "anthropic")
        if status == 429:
            raise RateLimitError(msg, "anthropic")
        if status == 400 and "context" in msg.lower():
            raise ContextLengthError(msg, "anthropic")
        raise ProviderError(msg, "anthropic", status_code=status, retryable=status >= 500)

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
