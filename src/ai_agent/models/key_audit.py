"""Validate API keys belong to the correct provider (shape + live probe)."""

from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

# field → provider
KEY_FIELD_PROVIDER = {
    "deepseek_api_key": "deepseek",
    "zai_api_key": "zai",
    "nvidia_api_key": "nvidia",
    "openai_api_key": "openai",
    "anthropic_api_key": "anthropic",
    "gemini_api_key": "gemini",
    "gemini_paid_api_key": "gemini_paid",
    "moonshot_api_key": "moonshot",
    "minimax_api_key": "minimax",
    "qwen_api_key": "qwen",
}

PROVIDER_LABEL = {
    "deepseek": "DeepSeek",
    "zai": "Z.AI",
    "nvidia": "NVIDIA",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Gemini",
    "gemini_paid": "Gemini (Paid)",
    "moonshot": "Moonshot",
    "minimax": "MiniMax",
    "qwen": "Qwen",
}

# Successful live probes: provider+key → monotonic timestamp. Speeds repeat Save.
_PROBE_OK_UNTIL: dict[str, float] = {}
_PROBE_TTL_SEC = 15 * 60
_PROBE_TIMEOUT = 5.0


def _cache_token(provider: str, api_key: str) -> str:
    digest = hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()[:24]
    return f"{provider}:{digest}"


def _cache_hit(provider: str, api_key: str) -> bool:
    token = _cache_token(provider, api_key)
    until = _PROBE_OK_UNTIL.get(token, 0.0)
    return until > time.monotonic()


def _cache_store(provider: str, api_key: str) -> None:
    _PROBE_OK_UNTIL[_cache_token(provider, api_key)] = time.monotonic() + _PROBE_TTL_SEC


def key_looks_like(provider: str, api_key: str) -> str | None:
    """Return error if key shape clearly belongs to another provider; else None."""
    key = (api_key or "").strip()
    if not key:
        return "API key is empty"
    low = key.lower()
    label = PROVIDER_LABEL.get(provider, provider)

    # Strong fingerprints — reject obvious mismatches.
    if low.startswith("nvapi-") and provider != "nvidia":
        return f"That looks like an NVIDIA NIM key (nvapi-…), not a {label} key."
    if low.startswith("sk-ant-") and provider != "anthropic":
        return f"That looks like an Anthropic key (sk-ant-…), not a {label} key."
    if low.startswith("aiza") and provider not in {"gemini", "gemini_paid"}:
        return f"That looks like a Gemini / Google AI key (AIza…), not a {label} key."
    if provider == "nvidia" and not low.startswith("nvapi-"):
        return "NVIDIA NIM keys start with nvapi-."
    if provider == "anthropic" and not low.startswith("sk-ant-"):
        return "Anthropic keys start with sk-ant-."
    if provider == "openai" and not (
        low.startswith("sk-") and not low.startswith("sk-ant-")
    ):
        return "OpenAI keys usually start with sk-."
    if provider == "deepseek" and not low.startswith("sk-"):
        return "DeepSeek keys usually start with sk-."
    if provider in {"gemini", "gemini_paid"} and low.startswith("nvapi-"):
        return "That is an NVIDIA key, not a Gemini key."
    if provider in {"gemini", "gemini_paid"} and low.startswith("sk-ant-"):
        return "That is an Anthropic key, not a Gemini key."
    # Z.AI keys are not Google AI Studio "AIza…" keys.
    if provider == "zai" and low.startswith("aiza"):
        return "That looks like a Gemini key. Paste your Z.AI key from https://z.ai for GLM models."
    if provider == "zai" and low.startswith("nvapi-"):
        return "That is an NVIDIA key. Paste your Z.AI key for GLM models."
    if len(key) < 16:
        return f"{label} API key looks too short."
    return None


def _status_from_get(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
) -> tuple[int, str]:
    """Auth check via GET — read status only; skip downloading huge /models bodies."""
    with client.stream("GET", url, headers=headers) as res:
        code = res.status_code
        body = ""
        if code >= 400:
            try:
                body = res.read().decode("utf-8", "replace")[:200]
            except Exception:
                body = ""
        return code, body


def probe_key(
    provider: str,
    api_key: str,
    *,
    base_urls: dict[str, str] | None = None,
    use_cache: bool = True,
) -> str | None:
    """Live-check that the key authenticates with the provider. Returns error or None."""
    shape = key_looks_like(provider, api_key)
    if shape:
        return shape
    key = api_key.strip()
    if use_cache and _cache_hit(provider, key):
        return None
    bases = base_urls or {}
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT) as client:
            if provider == "zai":
                url = (bases.get("zai") or "https://api.z.ai/api/paas/v4").rstrip("/")
                res = client.post(
                    f"{url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Accept-Language": "en-US,en",
                    },
                    json={
                        "model": "glm-4.5-flash",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                        "thinking": {"type": "disabled"},
                    },
                )
                code, body = res.status_code, (res.text or "")[:200]
            elif provider in {"gemini", "gemini_paid"}:
                url = (
                    bases.get("gemini")
                    or bases.get("gemini_paid")
                    or "https://generativelanguage.googleapis.com/v1beta/openai"
                ).rstrip("/")
                code, body = _status_from_get(
                    client, f"{url}/models", {"Authorization": f"Bearer {key}"}
                )
            elif provider == "nvidia":
                url = (bases.get("nvidia") or "https://integrate.api.nvidia.com/v1").rstrip(
                    "/"
                )
                code, body = _status_from_get(
                    client, f"{url}/models", {"Authorization": f"Bearer {key}"}
                )
            elif provider == "deepseek":
                url = (bases.get("deepseek") or "https://api.deepseek.com").rstrip("/")
                code, body = _status_from_get(
                    client, f"{url}/models", {"Authorization": f"Bearer {key}"}
                )
            elif provider == "openai":
                url = (bases.get("openai") or "https://api.openai.com/v1").rstrip("/")
                code, body = _status_from_get(
                    client, f"{url}/models", {"Authorization": f"Bearer {key}"}
                )
            elif provider == "anthropic":
                url = (bases.get("anthropic") or "https://api.anthropic.com").rstrip("/")
                code, body = _status_from_get(
                    client,
                    f"{url}/v1/models",
                    {
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                    },
                )
            elif provider == "moonshot":
                url = (bases.get("moonshot") or "https://api.moonshot.ai/v1").rstrip("/")
                code, body = _status_from_get(
                    client, f"{url}/models", {"Authorization": f"Bearer {key}"}
                )
            elif provider == "minimax":
                url = (
                    bases.get("minimax") or "https://api.minimax.io/v1"
                ).rstrip("/")
                code, body = _status_from_get(
                    client, f"{url}/models", {"Authorization": f"Bearer {key}"}
                )
            elif provider == "qwen":
                url = (
                    bases.get("qwen")
                    or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
                ).rstrip("/")
                code, body = _status_from_get(
                    client, f"{url}/models", {"Authorization": f"Bearer {key}"}
                )
            else:
                return None
    except httpx.TimeoutException:
        # Don't block Save on a slow provider — shape already looked OK.
        return None
    except httpx.HTTPError as exc:
        return f"{PROVIDER_LABEL.get(provider, provider)} key check failed (network: {exc.__class__.__name__})."

    label = PROVIDER_LABEL.get(provider, provider)
    if code in {401, 403}:
        return (
            f"This key was rejected by {label} (HTTP {code}). "
            f"Paste a real {label} API key — not a key from another provider."
        )
    # Transient overload / rate limits still mean the key was accepted enough to auth.
    if code in {408, 425, 429}:
        _cache_store(provider, key)
        return None
    if code >= 500:
        return None  # provider outage — don't block save
    if code >= 400 and provider == "zai":
        low = (body or "").lower()
        if any(
            t in low
            for t in (
                "unauthorized",
                "invalid",
                "api key",
                "authentication",
                "401",
                "403",
            )
        ):
            return f"This key was rejected by {label}. Use your Z.AI key for GLM models."
        return None
    if code >= 400:
        return f"{label} key check failed (HTTP {code}): {body}"
    _cache_store(provider, key)
    return None


def validate_key_for_field(
    field: str,
    api_key: str,
    *,
    base_urls: dict[str, str] | None = None,
    live: bool = True,
) -> str | None:
    provider = KEY_FIELD_PROVIDER.get(field)
    if not provider:
        return f"Unknown key field {field}"
    err = key_looks_like(provider, api_key)
    if err:
        return err
    if live:
        return probe_key(provider, api_key, base_urls=base_urls)
    return None


def assert_model_key_matches(
    *,
    model_id: str,
    provider: str,
    api_key: str,
    base_urls: dict[str, str] | None = None,
    live: bool = True,
) -> None:
    """Raise ValueError if the key cannot drive this model/provider."""
    label = PROVIDER_LABEL.get(provider, provider)
    if not (api_key or "").strip():
        raise ValueError(f"{label} API key is missing for model “{model_id}”.")
    err = key_looks_like(provider, api_key)
    if err:
        raise ValueError(
            f"Wrong key for model “{model_id}” ({label}): {err}"
        )
    if not live:
        return
    err = probe_key(provider, api_key, base_urls=base_urls)
    if err:
        raise ValueError(
            f"Key rejected for model “{model_id}” ({label}): {err}"
        )
