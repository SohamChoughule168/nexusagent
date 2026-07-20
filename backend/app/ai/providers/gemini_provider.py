"""Google Gemini provider.

Gemini's Generative Language API is neither OpenAI- nor Anthropic-shaped, so it
gets its own implementation of :class:`BaseLLMProvider`. The mapping converts
our provider-agnostic ``Message`` list into Gemini ``contents`` and back,
including tool-call (``functionCall`` / ``functionResponse``) round-trips.
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

_MODEL_CONTEXT_WINDOWS = {
    "gemini-1.5-pro": 2_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.0-flash-lite": 1_000_000,
}
_MODEL_PRICING = {
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
}


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Generative Language API provider."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        super().__init__(api_key, base_url)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"content-type": "application/json"},
            timeout=httpx.Timeout(120.0),
        )

    @property
    def provider_type(self):
        return ProviderType.GOOGLE

    def normalize_model_name(self, model: str) -> str:
        return model or self.DEFAULT_MODEL

    # -- request shaping ------------------------------------------------ #
    def _to_gemini(self, request: GenerationRequest):
        model = self.normalize_model_name(request.model)
        system_instruction = None
        contents: List[Dict[str, Any]] = []

        for msg in request.messages:
            role = msg.role.value
            if role == "system":
                system_instruction = {"parts": [{"text": msg.content}]}
                continue
            contents.append(self._convert_message(msg))

        payload: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        gen_cfg: Dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens:
            gen_cfg["maxOutputTokens"] = request.max_tokens
        if request.top_p is not None:
            gen_cfg["topP"] = request.top_p
        if request.stop_sequences:
            gen_cfg["stopSequences"] = request.stop_sequences
        payload["generationConfig"] = gen_cfg
        if request.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["function"]["name"],
                            "description": t["function"].get("description", ""),
                            "parameters": t["function"].get("parameters", {}),
                        }
                        for t in request.tools
                    ]
                }
            ]
        return model, payload

    def _convert_message(self, msg: Message) -> Dict[str, Any]:
        role = msg.role.value
        if role == "tool":
            return {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": msg.name or "tool",
                            "response": {"result": msg.content},
                        }
                    }
                ],
            }
        parts: List[Dict[str, Any]] = []
        if msg.content:
            parts.append({"text": msg.content})
        if msg.tool_calls:
            for tc in msg.tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                parts.append({"functionCall": {"name": fn.get("name"), "args": args}})
        gemini_role = "model" if role == "assistant" else "user"
        return {"role": gemini_role, "parts": parts}

    # -- response parsing ---------------------------------------------- #
    def _parse_candidates(self, data: Dict[str, Any]):
        candidates = data.get("candidates", [])
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        finish_reason = None
        if candidates:
            finish_reason = candidates[0].get("finishReason")
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    text_parts.append(part["text"])
                if "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append(
                        {
                            "id": fc.get("name"),
                            "type": "function",
                            "function": {
                                "name": fc.get("name"),
                                "arguments": json.dumps(fc.get("args", {})),
                            },
                        }
                    )
        usage = self._usage(data)
        return "".join(text_parts), tool_calls, usage, finish_reason

    def _usage(self, data: Dict[str, Any]) -> TokenUsage:
        u = data.get("usageMetadata", {}) or {}
        pt = u.get("promptTokenCount", 0)
        ct = u.get("candidatesTokenCount", 0)
        return TokenUsage(prompt_tokens=pt, completion_tokens=ct, total_tokens=u.get("totalTokenCount", pt + ct))

    def _url(self, model: str, stream: bool) -> str:
        verb = "streamGenerateContent" if stream else "generateContent"
        suffix = "?alt=sse" if stream else ""
        return f"/v1beta/models/{model}:{verb}?key={self.api_key}{suffix}"

    # -- interface ------------------------------------------------------ #
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        model, payload = self._to_gemini(request)
        try:
            resp = await self.client.post(self._url(model, False), json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            self._handle_error(e)
            return
        except httpx.TimeoutException:
            raise ProviderError("Request timed out", "google", status_code=408, retryable=True)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Unexpected error: {str(e)}", "google", retryable=True)
        content, tool_calls, usage, finish = self._parse_candidates(data)
        return GenerationResponse(
            content=content, tool_calls=tool_calls, token_usage=usage,
            finish_reason=finish, model=model,
            cost_usd=self.calculate_cost(model, usage), raw_response=data,
        )

    async def stream(self, request: GenerationRequest) -> AsyncGenerator[StreamChunk, None]:
        model, payload = self._to_gemini(request)
        try:
            async with self.client.stream("POST", self._url(model, True), json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    for chunk in self._parse_sse_line(line, model):
                        yield chunk
        except httpx.HTTPStatusError as e:
            self._handle_error(e)
        except httpx.TimeoutException:
            raise ProviderError("Stream timed out", "google", status_code=408, retryable=True)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Stream error: {str(e)}", "google", retryable=True)

    def _parse_sse_line(self, line: str, model: str) -> List[StreamChunk]:
        if not line or not line.startswith("data: "):
            return []
        raw = line[6:].strip()
        if raw == "[DONE]":
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if "candidates" not in data:
            # Usage-only stream chunks.
            if "usageMetadata" in data:
                u = data["usageMetadata"]
                return [
                    StreamChunk(
                        token_usage=TokenUsage(
                            prompt_tokens=u.get("promptTokenCount", 0),
                            completion_tokens=u.get("candidatesTokenCount", 0),
                        ),
                        model=model,
                    )
                ]
            return []
        content, tool_calls, _usage, finish = self._parse_candidates(data)
        if content:
            return [StreamChunk(delta_content=content, finish_reason=finish, model=model)]
        return []

    def supports_tools(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return True

    def get_max_context_window(self, model: str) -> int:
        return _MODEL_CONTEXT_WINDOWS.get(self.normalize_model_name(model), 1_000_000)

    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        pricing = _MODEL_PRICING.get(self.normalize_model_name(model))
        if not pricing:
            return 0.0
        in_p, out_p = pricing
        return (usage.prompt_tokens / 1_000_000) * in_p + (usage.completion_tokens / 1_000_000) * out_p

    def _handle_error(self, error: httpx.HTTPStatusError):
        status = error.response.status_code
        try:
            detail = error.response.json().get("error", {})
            msg = detail.get("message", str(error))
        except Exception:  # noqa: BLE001
            msg = str(error)
        if status == 401:
            raise AuthenticationError(msg, "google")
        if status == 404:
            raise ModelNotFoundError(msg, "google")
        if status == 429:
            raise RateLimitError(msg, "google")
        if status == 400 and "context" in msg.lower():
            raise ContextLengthError(msg, "google")
        raise ProviderError(msg, "google", status_code=status, retryable=status >= 500)

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
