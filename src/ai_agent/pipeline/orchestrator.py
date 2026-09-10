from __future__ import annotations

from typing import Any

from ai_agent.config import get_settings
from ai_agent.jobs.store import JobStore
from ai_agent.models.registry import ModelRegistry
from ai_agent.pipeline.copy_generator import generate_copy, result_to_dict
from ai_agent.redact import redact


DEFAULT_EVAL_MODELS = ["nvidia-nemotron-super-49b", "glm-4.7-flash", "nvidia-minimax-m3"]


def run_job(store: JobStore, job_id: str) -> None:
    rec = store.get(job_id)
    if rec is None:
        return
    store.update(job_id, status="running", progress="started")
    try:
        if rec.job_type == "write_eval":
            result = _run_write_eval(rec.request)
        elif rec.job_type in ("build_site", "build_page"):
            result = {
                "status": "not_implemented",
                "reason": "WordPress build pipeline waits for WP_SITE_URL and application password",
            }
        elif rec.job_type == "refine_section":
            result = {
                "status": "deferred",
                "reason": "refine_section is defined but not in v1 (design §8)",
            }
        else:
            raise ValueError(f"Unsupported job_type: {rec.job_type}")
        status = "succeeded"
        if rec.job_type in ("build_site", "build_page", "refine_section"):
            status = "partially_succeeded"
        store.update(job_id, status=status, result=result, progress="done")
    except Exception as exc:  # noqa: BLE001 — job boundary
        store.update(
            job_id,
            status="failed",
            error=redact(str(exc)),
            progress="failed",
        )


def _run_write_eval(request: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    options = request.get("options") or {}
    models = options.get("models") or []
    if not models:
        models = [settings.writer_model or settings.default_copy_model, settings.verifier_model]
        models = list(dict.fromkeys(models)) or DEFAULT_EVAL_MODELS
    hearing = (request.get("input") or {}).get("data") or {}
    page = hearing.get("target_page") or "top"

    registry = ModelRegistry(settings)
    runs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for model_id in models:
        try:
            result = generate_copy(registry, model_id, hearing, page=page)
            runs.append(result_to_dict(result))
        except Exception as exc:  # noqa: BLE001
            errors.append({"model": model_id, "error": redact(str(exc))})

    return {
        "page": page,
        "models_requested": models,
        "runs": runs,
        "errors": errors,
        "axes": [
            "japanese_quality",
            "factuality",
            "brand_constraints",
            "yakuji_safety",
            "token_cost",
            "latency",
        ],
        "note": "Structure is auto-scored (tokens/cost/latency). Japanese quality still needs human review.",
    }
