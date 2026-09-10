from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_agent.config import Settings, get_settings
from ai_agent.models.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    anthropic_provider,
    deepseek_provider,
    gemini_paid_provider,
    gemini_provider,
    minimax_provider,
    moonshot_provider,
    nvidia_provider,
    openai_provider,
    qwen_provider,
    zai_provider,
)
from ai_agent.models.types import ChatMessage, ChatResult


@dataclass(frozen=True)
class ModelBinding:
    id: str
    provider_name: str
    role: str
    name: str
    notes: str = ""
    # Only the provider's exact endpoint model string when it differs in spelling/path
    # (e.g. NIM "org/name"). NEVER use this to substitute a different model family.
    api_model: str | None = None

    @property
    def remote_id(self) -> str:
        return self.api_model or self.id

    @property
    def display_name(self) -> str:
        return self.name or self.id


# Role-based registry. Models are not hardcoded into pipeline steps.
REGISTRY: dict[str, ModelBinding] = {
    "deepseek-v4-flash": ModelBinding(
        "deepseek-v4-flash",
        "deepseek",
        "copy",
        "DeepSeek V4 Flash",
        "official DeepSeek API (prepaid)",
    ),
    "deepseek-v4-pro": ModelBinding(
        "deepseek-v4-pro",
        "deepseek",
        "copy",
        "DeepSeek V4 Pro",
        "official DeepSeek Pro (prepaid)",
    ),
    "nvidia-deepseek-v4-flash": ModelBinding(
        "nvidia-deepseek-v4-flash",
        "nvidia",
        "copy",
        "DeepSeek V4 Flash (NIM)",
        "free NIM DeepSeek V4 Flash 0731 (slow first token)",
        api_model="deepseek-ai/deepseek-v4-flash-0731",
    ),
    "nvidia-nemotron-3-super-120b": ModelBinding(
        "nvidia-nemotron-3-super-120b",
        "nvidia",
        "copy",
        "Nemotron 3 Super 120B (NIM)",
        "free — Nemotron 3 Super via NVIDIA NIM",
        api_model="nvidia/nemotron-3-super-120b-a12b",
    ),
    "nvidia-nemotron-super-49b": ModelBinding(
        "nvidia-nemotron-super-49b",
        "nvidia",
        "copy",
        "Nemotron Super 49B (NIM)",
        "free — Nemotron Super 49B via NVIDIA NIM",
        api_model="nvidia/llama-3.3-nemotron-super-49b-v1",
    ),
    # Official NVIDIA Nemotron (same API host; paid catalog for customer nvapi key)
    "nemotron-3-super-120b": ModelBinding(
        "nemotron-3-super-120b",
        "nvidia",
        "copy",
        "Nemotron 3 Super 120B",
        "paid — NVIDIA official API (customer key)",
        api_model="nvidia/nemotron-3-super-120b-a12b",
    ),
    "nemotron-super-49b": ModelBinding(
        "nemotron-super-49b",
        "nvidia",
        "copy",
        "Nemotron Super 49B",
        "paid — NVIDIA official API (customer key)",
        api_model="nvidia/llama-3.3-nemotron-super-49b-v1",
    ),
    # nvidia-glm-5.2 (z-ai/glm-5.2) removed: NIM returns 404 for many accounts / API deprecated.
    "glm-4.7-flash": ModelBinding(
        "glm-4.7-flash",
        "zai",
        "copy",
        "GLM-4.7 Flash",
        "free Z.AI Flash — must-have for PoC",
    ),
    "glm-4.5-flash": ModelBinding(
        "glm-4.5-flash",
        "zai",
        "copy",
        "GLM-4.5 Flash",
        "free Z.AI Flash backup",
    ),
    # Official Z.AI paid text models (api.z.ai)
    "glm-5.3": ModelBinding(
        "glm-5.3",
        "zai",
        "copy",
        "GLM-5.3",
        "paid Z.AI flagship — $1.40/$4.40 per 1M",
    ),
    "glm-5.2": ModelBinding(
        "glm-5.2",
        "zai",
        "copy",
        "GLM-5.2",
        "paid Z.AI official — $1.40/$4.40 per 1M",
    ),
    "glm-5.1": ModelBinding(
        "glm-5.1",
        "zai",
        "copy",
        "GLM-5.1",
        "paid Z.AI official — $1.40/$4.40 per 1M",
    ),
    "glm-5": ModelBinding(
        "glm-5",
        "zai",
        "copy",
        "GLM-5",
        "paid Z.AI official — $1.00/$3.20 per 1M",
    ),
    "glm-5-turbo": ModelBinding(
        "glm-5-turbo",
        "zai",
        "copy",
        "GLM-5 Turbo",
        "paid Z.AI official — $1.20/$4.00 per 1M",
    ),
    # Paid Z.AI 4.x removed from UI: free Flash covers 4.5/4.7 (no Free/Paid duplicate).
    "gpt-5.6-terra": ModelBinding(
        "gpt-5.6-terra",
        "openai",
        "copy",
        "GPT-5.6 Terra",
        "OpenAI balanced writer",
    ),
    "gpt-5.6-sol": ModelBinding(
        "gpt-5.6-sol",
        "openai",
        "copy",
        "GPT-5.6 Sol",
        "OpenAI top-tier writer",
    ),
    "gpt-5.6-luna": ModelBinding(
        "gpt-5.6-luna",
        "openai",
        "copy",
        "GPT-5.6 Luna",
        "OpenAI volume writer",
    ),
    "gemini-3.5-flash-lite": ModelBinding(
        "gemini-3.5-flash-lite",
        "gemini",
        "copy",
        "Gemini 3.5 Flash-Lite",
        "free — fastest Gemini Flash-Lite for PoC drafts",
    ),
    "gemini-3.5-flash": ModelBinding(
        "gemini-3.5-flash",
        "gemini",
        "copy",
        "Gemini 3.5 Flash",
        "free — stronger Japanese copy than Flash-Lite",
    ),
    # Paid menu only — uses GEMINI_PAID_API_KEY (never the free Flash key).
    "gemini-3.5-flash-lite-paid": ModelBinding(
        "gemini-3.5-flash-lite-paid",
        "gemini_paid",
        "copy",
        "Gemini 3.5 Flash-Lite",
        "paid — Flash-Lite on client billed key",
        api_model="gemini-3.5-flash-lite",
    ),
    "gemini-3.5-flash-paid": ModelBinding(
        "gemini-3.5-flash-paid",
        "gemini_paid",
        "copy",
        "Gemini 3.5 Flash",
        "paid — Flash 3.5 on client billed key",
        api_model="gemini-3.5-flash",
    ),
    "gemini-3.6-flash": ModelBinding(
        "gemini-3.6-flash",
        "gemini_paid",
        "copy",
        "Gemini 3.6 Flash",
        "paid — client Gemini billed key",
    ),
    "gemini-3.7-flash": ModelBinding(
        "gemini-3.7-flash",
        "gemini_paid",
        "copy",
        "Gemini 3.7 Flash",
        "paid — client Gemini billed key",
    ),
    "gemini-3.8-flash": ModelBinding(
        "gemini-3.8-flash",
        "gemini_paid",
        "copy",
        "Gemini 3.8 Flash",
        "paid — latest Gemini Flash (client billed key)",
    ),
    "gemini-3.1-pro-preview": ModelBinding(
        "gemini-3.1-pro-preview",
        "gemini_paid",
        "copy",
        "Gemini 3.1 Pro Preview",
        "paid — highest-quality Gemini in this list",
    ),
    "kimi-k3": ModelBinding(
        "kimi-k3",
        "moonshot",
        "copy",
        "Kimi K3",
        "paid — Moonshot Kimi K3 (official API)",
        api_model="kimi-k3",
    ),
    "nvidia-kimi-k3": ModelBinding(
        "nvidia-kimi-k3",
        "nvidia",
        "copy",
        "Kimi K3 (NIM)",
        "free — Kimi K3 via NVIDIA NIM (verified)",
        api_model="moonshotai/kimi-k3",
    ),
    "minimax-m3": ModelBinding(
        "minimax-m3",
        "minimax",
        "copy",
        "MiniMax M3",
        "paid — MiniMax M3 (official API)",
        api_model="MiniMax-M3",
    ),
    "nvidia-minimax-m3": ModelBinding(
        "nvidia-minimax-m3",
        "nvidia",
        "copy",
        "MiniMax M3 (NIM)",
        "free — MiniMax M3 via NVIDIA NIM (verified)",
        api_model="minimaxai/minimax-m3",
    ),
    "qwen-flash": ModelBinding(
        "qwen-flash",
        "qwen",
        "copy",
        "Qwen Flash",
        "paid — Qwen-Flash (DashScope; trial quota then metered)",
    ),
    "qwen-plus": ModelBinding(
        "qwen-plus",
        "qwen",
        "copy",
        "Qwen Plus",
        "paid — Qwen-Plus (DashScope; trial quota then metered)",
    ),
    "claude-sonnet-5": ModelBinding(
        "claude-sonnet-5",
        "anthropic",
        "copy",
        "Claude Sonnet 5",
        "Claude Sonnet 5",
    ),
    "claude-haiku-4.5": ModelBinding(
        "claude-haiku-4.5",
        "anthropic",
        "copy",
        "Claude Haiku 4.5",
        "Claude Haiku 4.5",
        api_model="claude-haiku-4-5",  # Anthropic API id uses hyphen
    ),
    "claude-opus-4.5": ModelBinding(
        "claude-opus-4.5",
        "anthropic",
        "copy",
        "Claude Opus 4.5",
        "paid — Claude Opus 4.5",
        api_model="claude-opus-4-5",  # Anthropic API id uses hyphen
    ),
    "claude-opus-5": ModelBinding(
        "claude-opus-5",
        "anthropic",
        "copy",
        "Claude Opus 5",
        "paid — Claude Opus 5 (flagship)",
        api_model="claude-opus-5",
    ),
}


class ModelRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._providers: dict[str, Any] = {
            "deepseek": deepseek_provider(self.settings),
            "zai": zai_provider(self.settings),
            "nvidia": nvidia_provider(self.settings),
            "openai": openai_provider(self.settings),
            "gemini": gemini_provider(self.settings),
            "gemini_paid": gemini_paid_provider(self.settings),
            "moonshot": moonshot_provider(self.settings),
            "minimax": minimax_provider(self.settings),
            "qwen": qwen_provider(self.settings),
            "anthropic": anthropic_provider(self.settings),
        }

    def resolve(self, model_id: str) -> tuple[Any, ModelBinding]:
        binding = REGISTRY.get(model_id)
        if not binding:
            known = ", ".join(sorted(REGISTRY))
            raise KeyError(f"Unknown model {model_id!r}. Known: {known}")
        return self._providers[binding.provider_name], binding

    def chat(self, model_id: str, messages: list[ChatMessage], **kwargs) -> ChatResult:
        from ai_agent.models.quota_tracker import record_failure, record_success

        provider, binding = self.resolve(model_id)
        try:
            result = provider.chat(binding.remote_id, messages, **kwargs)
            result.model = model_id
            record_success(model_id)
            return result
        except Exception as exc:
            record_failure(model_id, str(exc))
            raise

    async def chat_stream(self, model_id: str, messages: list[ChatMessage], **kwargs):
        from ai_agent.models.quota_tracker import record_failure, record_success

        provider, binding = self.resolve(model_id)
        try:
            async for token in provider.chat_stream(
                binding.remote_id, messages, **kwargs
            ):
                yield token
            record_success(model_id)
        except Exception as exc:
            record_failure(model_id, str(exc))
            raise

    def available(self) -> list[dict[str, str]]:
        out = []
        for model_id, binding in REGISTRY.items():
            provider = self._providers[binding.provider_name]
            out.append(
                {
                    "id": model_id,
                    "name": binding.display_name,
                    "provider": binding.provider_name,
                    "role": binding.role,
                    "notes": binding.notes,
                    "key_configured": bool(getattr(provider, "api_key", "")),
                }
            )
        return out
