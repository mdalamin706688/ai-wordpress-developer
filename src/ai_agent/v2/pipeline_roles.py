"""V2 lab model roles — 1 or 2 models only (not v1 multi-model stack)."""

from __future__ import annotations

from ai_agent.api.lab import REGISTRY

V2_MAX_MODELS = 2


class V2ModelRoleError(ValueError):
    """Invalid model slot assignment for satellite lab."""


def v2_model_ids(model_ids: list[str]) -> list[str]:
    return [m for m in model_ids if m in REGISTRY][:V2_MAX_MODELS]


def v2_planner_model(model_ids: list[str]) -> str:
    """Model #1 — AI-1 section creator (structure + rules only, never page copy)."""
    ids = v2_model_ids(model_ids)
    return ids[0] if ids else ""


def v2_writer_model(model_ids: list[str]) -> str:
    """Model #2 — AI-2 content writer (Japanese section text only)."""
    ids = v2_model_ids(model_ids)
    return ids[1] if len(ids) >= 2 else ""


def validate_v2_model_roles(model_ids: list[str]) -> tuple[str, str]:
    """Return (planner, writer). Writer empty when only one model."""
    ids = v2_model_ids(model_ids)
    if not ids:
        return "", ""
    planner = ids[0]
    writer = ids[1] if len(ids) >= 2 else ""
    if writer and planner == writer:
        raise V2ModelRoleError(
            "Model #1 and #2 must be different: #1 = section creator (structure only), "
            "#2 = content writer (Japanese text)."
        )
    return planner, writer


def v2_pipeline_roles(model_ids: list[str]) -> tuple[str, str, list[str], str]:
    """Map selected models to v2 roles.

    - 1 model  → AI-1 section planner only (no AI-2 content)
    - 2 models → #1 AI-1 section planner, #2 content writer

    Returns (writer, quality_writer, verifier_pool, mode).
    """
    ids = v2_model_ids(model_ids)
    if not ids:
        return "", "", [], "none"
    if len(ids) == 1:
        return "", "", [], "sections_only"
    try:
        _, writer = validate_v2_model_roles(ids)
    except V2ModelRoleError:
        return "", "", [], "none"
    return writer, "", [], "write"


def v2_active_model_ids(model_ids: list[str]) -> list[str]:
    """Models that participate in AI-2 Draft — writer (#2) only."""
    writer = v2_writer_model(model_ids)
    return [writer] if writer else []


def v2_planner_model_ids(model_ids: list[str]) -> list[str]:
    """Models required for AI-1 blueprint — planner (#1) only."""
    planner = v2_planner_model(model_ids)
    return [planner] if planner else []
