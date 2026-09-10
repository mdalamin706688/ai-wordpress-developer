from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ai_agent.config import Settings, get_settings
from ai_agent.models.types import ChatMessage, ChatResult, Usage, estimate_cost_usd


RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
NON_RETRYABLE_STATUS = frozenset({400, 401, 403})
MAX_CHAT_ATTEMPTS = 4
_RETRY_IN_RE = re.compile(r"retry in\s+([0-9]+(?:\.[0-9]+)?)\s*s", re.I)


def retry_sleep_seconds(status_code: int, body: str = "", attempt: int = 0) -> float:
    """Honor provider retry-after hints (Gemini 429 often asks for 20–60s)."""
    if status_code == 429:
        match = _RETRY_IN_RE.search(body or "")
        if match:
            # Free Flash 3.6+ often needs the full suggested wait (+ small buffer).
            return min(75.0, float(match.group(1)) + 2.0)
        return min(55.0, 10.0 * (2 ** attempt))
    return min(8.0, 0.8 * (2 ** attempt))


def should_retry_status(status_code: int, body: str = "") -> bool:
    if status_code in NON_RETRYABLE_STATUS:
        return False
    if status_code in RETRYABLE_STATUS:
        return True
    low = (body or "").lower()
    if "invalid api key" in low or "invalid_api_key" in low:
        return False
    return any(
        token in low
        for token in (
            "overloaded",
            "too many requests",
            "try again later",
            "rate limit",
            '"code":"1305"',
            'code":1305',
        )
    )


def should_retry_exception(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.ReadError,
            ConnectionResetError,
            TimeoutError,
        ),
    ):
        return True
    text = str(exc).lower()
    return "connection reset" in text or "timed out" in text or "timeout" in text


class LLMError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    """DeepSeek and Z.AI both speak OpenAI chat-completions."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        timeout_sec: float | httpx.Timeout,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = (
            timeout_sec
            if isinstance(timeout_sec, httpx.Timeout)
            else httpx.Timeout(timeout_sec)
        )
        self.timeout_sec = (
            timeout_sec.read
            if isinstance(timeout_sec, httpx.Timeout)
            else float(timeout_sec)
        )
        self.extra_headers = extra_headers or {}
        self.extra_body = extra_body or {}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def _payload(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool = False,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **self.extra_body,
            **(extra_body or {}),
        }
        if self.name == "nvidia" and "chat_template_kwargs" not in payload:
            low = model.lower()
            if "deepseek" in low or "kimi" in low:
                payload["chat_template_kwargs"] = {"thinking": False}
            elif "nemotron" in low:
                payload["chat_template_kwargs"] = {
                    "enable_thinking": False,
                    "thinking": False,
                }
        # Z.AI GLM Flash returns empty content / 429 more often with thinking on.
        if self.name == "zai" and "thinking" not in payload:
            low = model.lower()
            if "flash" in low or low.startswith("glm-4."):
                payload["thinking"] = {"type": "disabled"}
        if stream:
            payload["stream"] = True
        return payload

    def _is_retryable_error(self, status_code: int, body: str) -> bool:
        return should_retry_status(status_code, body)

    def _post_chat_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        attempts: int = MAX_CHAT_ATTEMPTS,
    ) -> dict[str, Any]:
        last_err = ""
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=self._headers(), json=payload)
            except httpx.HTTPError as exc:
                last_err = str(exc)
                if should_retry_exception(exc) and attempt + 1 < attempts:
                    time.sleep(min(8.0, 0.6 * (2 ** attempt)))
                    continue
                raise LLMError(f"{self.name} request failed: {exc}") from exc
            if response.status_code < 400:
                return response.json()
            body = response.text[:800]
            last_err = f"{self.name} HTTP {response.status_code}: {body}"
            try:
                from ai_agent.models.quota_tracker import note_http_error

                note_http_error(
                    str(payload.get("model") or ""),
                    int(response.status_code),
                    body,
                )
            except Exception:
                pass
            if should_retry_status(response.status_code, body) and attempt + 1 < attempts:
                time.sleep(retry_sleep_seconds(response.status_code, body, attempt))
                continue
            raise LLMError(last_err)
        raise LLMError(last_err or f"{self.name} request failed")

    def _delta_text(self, line: str) -> str | None:
        if not line or line.startswith(":") or not line.startswith("data:"):
            return None
        data = line[5:].strip()
        if data == "[DONE]":
            return ""
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return None
        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
        text = delta.get("content") or ""
        if isinstance(text, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )
        return str(text) if str(text) else None

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        extra_body: dict[str, Any] | None = None,
    ) -> ChatResult:
        if not self.api_key:
            raise LLMError(f"{self.name} API key is missing")

        url = f"{self.base_url}/chat/completions"
        payload = self._payload(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )

        started = time.perf_counter()
        try:
            if self.name == "nvidia":
                return self._chat_via_stream(
                    model,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                    started=started,
                )
            body = self._post_chat_json(url, payload)
        except LLMError as exc:
            text = str(exc)
            if (
                extra_body
                and extra_body.get("reasoning_effort") == "minimal"
                and "HTTP 400" in text
                and "thinking level" in text.lower()
            ):
                fallback = {**extra_body, "reasoning_effort": "low"}
                payload = self._payload(
                    model,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra_body=fallback,
                )
                body = self._post_chat_json(url, payload)
            else:
                raise
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} request failed: {exc}") from exc

        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if not str(content).strip():
            content = message.get("reasoning_content") or ""
        usage_raw = body.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
            completion_tokens=int(usage_raw.get("completion_tokens") or 0),
            total_tokens=int(usage_raw.get("total_tokens") or 0),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = ChatResult(
            model=model,
            provider=self.name,
            content=str(content).strip(),
            usage=usage,
            latency_ms=latency_ms,
            raw={"id": body.get("id"), "created": body.get("created")},
        )
        result.estimated_usd = round(estimate_cost_usd(model, usage), 6)
        return result

    def _chat_via_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        extra_body: dict[str, Any] | None,
        started: float,
    ) -> ChatResult:
        """NVIDIA DeepSeek V4 Flash is slow to first token; streaming avoids a full-body timeout."""
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_body=extra_body,
        )
        chunks: list[str] = []
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, headers=self._headers(), json=payload) as response:
                    if response.status_code >= 400:
                        body = response.read().decode("utf-8", "replace")
                        raise LLMError(
                            f"{self.name} HTTP {response.status_code}: {body[:800]}"
                        )
                    for line in response.iter_lines():
                        text = self._delta_text(line)
                        if text:
                            chunks.append(text)
        except LLMError:
            raise
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} request failed: {exc}") from exc
        content = "".join(chunks).strip()
        if not content:
            raise LLMError(f"{self.name} streamed an empty response from {model}")
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = ChatResult(
            model=model,
            provider=self.name,
            content=content,
            usage=Usage(),
            latency_ms=latency_ms,
        )
        result.estimated_usd = round(estimate_cost_usd(model, result.usage), 6)
        return result

    async def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        extra_body: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise LLMError(f"{self.name} API key is missing")

        url = f"{self.base_url}/chat/completions"
        payload = self._payload(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_body=extra_body,
        )
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                async for token in self._iter_stream(url, payload):
                    yield token
                return
            except LLMError as exc:
                last_exc = exc
                text = str(exc)
                retryable = self._is_retryable_error(
                    429 if "HTTP 429" in text else 0,
                    text,
                ) or "HTTP 429" in text or "HTTP 503" in text or "overloaded" in text.lower()
                if extra_body and "thinking" in extra_body and "HTTP 400" in text:
                    payload.pop("thinking", None)
                    fallback = {k: v for k, v in extra_body.items() if k != "thinking"}
                    payload = self._payload(
                        model,
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        extra_body=fallback or None,
                    )
                    async for token in self._iter_stream(url, payload):
                        yield token
                    return
                # Gemini 3.8+ rejects reasoning_effort=minimal; remap once to low.
                if (
                    extra_body
                    and extra_body.get("reasoning_effort") == "minimal"
                    and "HTTP 400" in text
                    and "thinking level" in text.lower()
                ):
                    fallback = {**extra_body, "reasoning_effort": "low"}
                    payload = self._payload(
                        model,
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        extra_body=fallback,
                    )
                    extra_body = fallback
                    async for token in self._iter_stream(url, payload):
                        yield token
                    return
                if retryable and attempt + 1 < 4:
                    # Honor Gemini "Please retry in 25s" instead of tiny backoff.
                    wait = retry_sleep_seconds(
                        429 if "HTTP 429" in text else 503,
                        text,
                        attempt,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
        if last_exc:
            raise last_exc

    async def _iter_stream(
        self, url: str, payload: dict[str, Any]
    ) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(), json=payload
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", "replace")
                        try:
                            from ai_agent.models.quota_tracker import note_http_error

                            note_http_error(
                                str(payload.get("model") or ""),
                                int(response.status_code),
                                body,
                            )
                        except Exception:
                            pass
                        raise LLMError(
                            f"{self.name} HTTP {response.status_code}: {body[:800]}"
                        )
                    async for line in response.aiter_lines():
                        text = self._delta_text(line)
                        if text:
                            yield text
        except LLMError:
            raise
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} request failed: {exc}") from exc


def deepseek_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="deepseek",
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        timeout_sec=settings.request_timeout_sec,
    )


def zai_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="zai",
        base_url=settings.zai_base_url,
        api_key=settings.zai_api_key,
        timeout_sec=settings.request_timeout_sec,
        extra_headers={"Accept-Language": "en-US,en"},
    )


def nvidia_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="nvidia",
        base_url=settings.nvidia_base_url,
        api_key=settings.nvidia_api_key,
        # DeepSeek V4 Flash 0731 is slow to first token; other NIM chat models are faster.
        timeout_sec=httpx.Timeout(connect=20.0, read=150.0, write=30.0, pool=20.0),
    )


def openai_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="openai",
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        timeout_sec=settings.request_timeout_sec,
    )


def gemini_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    """Google AI Studio / Gemini API via OpenAI-compatible endpoint.

    Free-tier Flash models. Accepts standard AI Studio keys (often AIza…) and newer AQ.… keys.
    Auth: Authorization Bearer <key> against
    https://generativelanguage.googleapis.com/v1beta/openai
    """
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="gemini",
        base_url=settings.gemini_base_url,
        api_key=(settings.gemini_api_key or "").strip(),
        timeout_sec=httpx.Timeout(connect=20.0, read=210.0, write=30.0, pool=20.0),
    )


def gemini_paid_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    """Billed Gemini key for paid catalog models only (3.6+ Flash, Pro, etc.)."""
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="gemini_paid",
        base_url=settings.gemini_base_url,
        api_key=(settings.gemini_paid_api_key or "").strip(),
        timeout_sec=httpx.Timeout(connect=20.0, read=210.0, write=30.0, pool=20.0),
    )


def moonshot_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="moonshot",
        base_url=settings.moonshot_base_url,
        api_key=settings.moonshot_api_key,
        timeout_sec=settings.request_timeout_sec,
    )


def minimax_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="minimax",
        base_url=settings.minimax_base_url,
        api_key=settings.minimax_api_key,
        timeout_sec=settings.request_timeout_sec,
    )


def qwen_provider(settings: Settings | None = None) -> OpenAICompatibleProvider:
    settings = settings or get_settings()
    return OpenAICompatibleProvider(
        name="qwen",
        base_url=settings.qwen_base_url,
        api_key=settings.qwen_api_key,
        timeout_sec=settings.request_timeout_sec,
    )


class AnthropicProvider:
    """Minimal Anthropic Messages API wrapper for lab runs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        timeout_sec: float = 120.0,
    ) -> None:
        self.name = "anthropic"
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_sec)

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        extra_body: dict[str, Any] | None = None,
    ) -> ChatResult:
        if not self.api_key:
            raise LLMError("anthropic API key is missing")
        system = ""
        converted: list[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                system = (system + "\n" + msg.content).strip() if system else msg.content
            else:
                converted.append({"role": msg.role, "content": msg.content})
        payload: dict[str, Any] = {
            "model": model,
            "messages": converted,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        if extra_body:
            payload.update(extra_body)
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"anthropic request failed: {exc}") from exc
        if response.status_code >= 400:
            raise LLMError(f"anthropic HTTP {response.status_code}: {response.text[:800]}")
        body = response.json()
        parts = body.get("content") or []
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in parts
        )
        usage_raw = body.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_raw.get("input_tokens") or 0),
            completion_tokens=int(usage_raw.get("output_tokens") or 0),
            total_tokens=int(usage_raw.get("input_tokens") or 0)
            + int(usage_raw.get("output_tokens") or 0),
        )
        result = ChatResult(
            model=model,
            provider=self.name,
            content=str(content).strip(),
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        result.estimated_usd = round(estimate_cost_usd(model, usage), 6)
        return result

    async def chat_stream(self, model: str, messages: list[ChatMessage], **kwargs):
        result = self.chat(model, messages, **kwargs)
        if result.content:
            yield result.content


def anthropic_provider(settings: Settings | None = None) -> AnthropicProvider:
    settings = settings or get_settings()
    return AnthropicProvider(
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,
        timeout_sec=settings.request_timeout_sec,
    )
