from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int:
        return self.completion_tokens


@dataclass
class ChatResult:
    model: str
    provider: str
    content: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
    estimated_usd: float | None = None


# USD per 1M tokens. Peak / cache-miss rates used for conservative PoC estimates.
# GLM Flash is billed $0 on Z.AI.
PRICING_USD_PER_M = {
    "deepseek-v4-flash": {"input": 0.44, "output": 1.32},
    "deepseek-v4-pro": {"input": 1.32, "output": 3.96},
    "glm-4.7-flash": {"input": 0.0, "output": 0.0},
    "glm-4.5-flash": {"input": 0.0, "output": 0.0},
    "glm-5.3": {"input": 1.40, "output": 4.40},
    "glm-5.2": {"input": 1.40, "output": 4.40},
    "glm-5.1": {"input": 1.40, "output": 4.40},
    "glm-5": {"input": 1.00, "output": 3.20},
    "glm-5-turbo": {"input": 1.20, "output": 4.00},
    "nvidia-nemotron-super-49b": {"input": 0.0, "output": 0.0},
    "nvidia/llama-3.3-nemotron-super-49b-v1": {"input": 0.0, "output": 0.0},
    "nemotron-super-49b": {"input": 0.0, "output": 0.0},
    "nemotron-3-super-120b": {"input": 0.0, "output": 0.0},
    "nvidia-kimi-k3": {"input": 0.0, "output": 0.0},
    "moonshotai/kimi-k3": {"input": 0.0, "output": 0.0},
    "nvidia-minimax-m3": {"input": 0.0, "output": 0.0},
    "minimaxai/minimax-m3": {"input": 0.0, "output": 0.0},
    "nvidia-deepseek-v4-flash": {"input": 0.0, "output": 0.0},
    "deepseek-ai/deepseek-v4-flash-0731": {"input": 0.0, "output": 0.0},
    "nvidia-nemotron-3-super-120b": {"input": 0.0, "output": 0.0},
    "nvidia/nemotron-3-super-120b-a12b": {"input": 0.0, "output": 0.0},
    # Gemini Flash / Flash-Lite: free tier ($0) in lab catalog (3.5 only).
    "gemini-3.5-flash-lite": {"input": 0.0, "output": 0.0},
    "gemini-3.5-flash": {"input": 0.0, "output": 0.0},
    "gemini-3.5-flash-lite-paid": {"input": 0.0, "output": 0.0},
    "gemini-3.5-flash-paid": {"input": 0.0, "output": 0.0},
    "gemini-3.6-flash": {"input": 0.0, "output": 0.0},
    "gemini-3.7-flash": {"input": 0.0, "output": 0.0},
    "gemini-3.8-flash": {"input": 0.0, "output": 0.0},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.0},
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-opus-4.5": {"input": 5.0, "output": 25.0},
    "qwen-flash": {"input": 0.05, "output": 0.40},
    "qwen-plus": {"input": 0.40, "output": 1.20},
}


def estimate_cost_usd(model: str, usage: Usage) -> float:
    rates = PRICING_USD_PER_M.get(model, {"input": 0.0, "output": 0.0})
    return (usage.prompt_tokens / 1_000_000) * rates["input"] + (
        usage.completion_tokens / 1_000_000
    ) * rates["output"]
