from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_agent.config import get_settings
from ai_agent.jobs.schemas import JobRecord, utcnow
from ai_agent.jobs.store import JobStore
from ai_agent.models.providers import LLMError
from ai_agent.models.registry import ModelRegistry
from ai_agent.pipeline.ai_stack import FREE_WRITER_CANDIDATES, run_copy_stack
from ai_agent.pipeline.copy_generator import demo_messages, parse_copy_json
from ai_agent.pipeline.hearing_adapter import (
    build_hearing_tables,
    canonical_hearing,
    parse_hearing_csv,
    prepare_hearing_for_production,
)
from ai_agent.pipeline.scoring import score_copy
from ai_agent.pipeline.site_composer import compose_site_draft, job_summary
from ai_agent.pipeline.validate import WP_ALLOWED_STATUSES, prepare_copy_for_wordpress
from ai_agent.wp.publisher import create_draft_pages
from ai_agent.redact import redact

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]
LAST_PATH = ROOT / "data" / "demo_last.json"
JSON_PATH = ROOT / "fixtures" / "hearing_salon.json"
CSV_PATH = ROOT / "fixtures" / "hearing_salon.csv"
SHEET_PATH = ROOT / "demo" / "hearing-sheet.csv"
_store = JobStore()

DEFAULT_COLORS = {
    "base": "#FBF7F0",
    "ink": "#2C2A26",
    "accent-1": "#2a7d4f",
    "accent-2": "#C4A574",
}

PIPELINE = [
    {"id": "hearing", "ja": "ヒアリングCSV", "en": "Hearing CSV", "phase": "before"},
    {"id": "admin", "ja": "Root Admin / API Bridge", "en": "Root Admin / API Bridge", "phase": "before"},
    {"id": "job", "ja": "AIジョブ開始", "en": "Start AI job", "phase": "before"},
    {"id": "agent", "ja": "AIが日本語を書く", "en": "AI writes Japanese", "phase": "before"},
    {"id": "review", "ja": "お客様が文章を判定", "en": "Client reviews the copy", "phase": "before"},
    {"id": "wordpress", "ja": "WordPress開始：下書き作成", "en": "WordPress starts: create drafts", "phase": "wp"},
    {"id": "compose", "ja": "ページ・文章・デザイン・メニュー", "en": "Pages + text + design + menu", "phase": "wp"},
    {"id": "draft", "ja": "すべて下書きで保存", "en": "Save everything as draft", "phase": "wp"},
    {"id": "summary", "ja": "状態と要約を返す", "en": "Return status + summary", "phase": "wp"},
    {"id": "human", "ja": "人が写真を入れる", "en": "Human adds images", "phase": "after"},
    {"id": "publish", "ja": "人が公開する", "en": "Human publishes", "phase": "after"},
]


class DemoGenerateIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    business_name: str
    industry: str = "relaxation_salon"
    area: str = ""
    tone: str = ""
    hours: str = ""
    services: list[str] | str = ""
    forbidden: list[str] | str = ""
    missing: list[str] | str = ""
    target_page: str = "top"
    colors: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_COLORS))
    catchcopy: str = ""
    address: str = ""
    station: str = ""
    phone: str = ""
    closed: str = ""
    parking: str = ""
    reservation: str = ""
    concept: str = ""
    payment: str = ""
    first_visit: str = ""
    target: str = ""
    atmosphere: list[str] | str = ""
    menu: list[dict[str, Any]] = Field(default_factory=list)

    def to_hearing(self) -> dict[str, Any]:
        data = self.model_dump()
        data["services"] = _as_list(data.get("services") or "")
        data["forbidden"] = _as_list(data.get("forbidden") or "")
        data["missing"] = _as_list(data.get("missing") or "")
        if isinstance(data.get("atmosphere"), str):
            data["atmosphere"] = _as_list(data["atmosphere"])
        if data.get("menu"):
            data["services"] = [
                str(item.get("name") or "").strip()
                for item in data["menu"]
                if isinstance(item, dict) and item.get("name")
            ] or data["services"]
        data["colors"] = {**DEFAULT_COLORS, **(data.get("colors") or {})}
        return data


class HearingParseIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    csv: str = ""
    json_data: Any = Field(default=None, alias="json")


class CompareIn(BaseModel):
    csv: str = ""
    hearing: dict[str, Any] | None = None
    models: list[str] = Field(default_factory=list)
    page: str = "top"


DEFAULT_COMPARE_MODELS = [
    "glm-4.5-flash",
    "glm-4.7-flash",
    "nvidia-minimax-m3",
    "nvidia-nemotron-super-49b",
    "nvidia-kimi-k3",
    "nvidia-deepseek-v4-flash",
]


def _as_list(value: list[str] | str) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    import re

    text = str(value or "").strip()
    if not text:
        return []
    return [
        part.strip()
        for part in re.split(r"[、;；]+|(?<!\d),(?!\d{3})", text)
        if part.strip()
    ]


def _fill_hearing_gaps(hearing: dict[str, Any]) -> dict[str, Any]:
    return prepare_hearing_for_production(hearing)


def _parse_hearing_csv(raw: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        hearing, meta = parse_hearing_csv(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _fill_hearing_gaps(hearing), meta


def _hearing_from_dict(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if data.get("hearing") and isinstance(data.get("hearing"), dict):
        data = data["hearing"]
    if str(data.get("business_name") or "").strip():
        hearing = DemoGenerateIn(**data).to_hearing()
        meta = {
            "source": "json",
            "profile": "canonical_json",
            "table": build_hearing_tables(hearing, None),
        }
        return _fill_hearing_gaps(hearing), meta
    raw = {str(key): "" if value is None else str(value) for key, value in data.items()}
    hearing, meta = canonical_hearing(raw, source="json")
    return _fill_hearing_gaps(hearing), meta


def _resolve_hearing(body: CompareIn) -> tuple[dict[str, Any], dict[str, Any]]:
    if body.hearing and str(body.hearing.get("business_name") or "").strip():
        hearing = _fill_hearing_gaps(dict(body.hearing))
        return hearing, {"source": "hearing_json", "profile": "provided"}
    if body.csv.strip():
        return _parse_hearing_csv(body.csv)
    raise HTTPException(status_code=400, detail="csv or hearing required")


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _friendly(exc: Exception) -> dict[str, str]:
    text = str(exc)
    lowered = text.lower()
    if "429" in text or "overloaded" in lowered:
        return {
            "en": "The writer is busy. Please try once more.",
            "ja": "混み合っています。もう一度お試しください。",
        }
    if "timeout" in lowered or "timed out" in lowered:
        return {
            "en": "This draft took too long. Please try once more.",
            "ja": "時間がかかりすぎました。もう一度お試しください。",
        }
    if "api key is missing" in lowered:
        return {
            "en": "The writer is not connected on this machine.",
            "ja": "この端末ではライターが未接続です。",
        }
    return {
        "en": "Could not finish this draft. Please try once more.",
        "ja": "下書きを作れませんでした。もう一度お試しください。",
    }


def load_sample_hearing() -> dict[str, Any]:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


@router.get("/v1/demo/status")
def demo_status() -> dict[str, Any]:
    settings = get_settings()
    registry = ModelRegistry(settings)
    writer_ok = any(
        item.get("key_configured")
        and item["id"] in {*FREE_WRITER_CANDIDATES, settings.default_copy_model}
        for item in registry.available()
    )
    return {
        "ok": writer_ok,
        "has_last_draft": LAST_PATH.is_file(),
        "pipeline": PIPELINE,
        "wordpress_connected": bool(settings.wp_site_url and settings.wp_app_password),
        "ai_stack": {
            "cost_usd": 0,
            "knowledge": "hearing_sheet_only",
            "stream_writer": "glm-4.5-flash",
            "quality_writer": "nvidia-nemotron-super-49b",
            "verifiers": [
                "glm-4.7-flash",
                "nvidia-nemotron-super-49b",
                "nvidia-kimi-k3",
            ],
            "profiles": ["salon", "hearing_sys", "infobix", "generic"],
            "compare_endpoint": "/v1/demo/compare",
        },
    }


@router.get("/v1/demo/hearing")
def demo_hearing() -> dict[str, Any]:
    return {
        "hearing": load_sample_hearing(),
        "source": "fixtures/hearing_salon.csv",
        "format": "csv",
        "download": "/v1/demo/hearing-sheet.csv",
    }


@router.get("/v1/demo/hearing.csv")
@router.get("/v1/demo/hearing-sheet.csv")
@router.get("/v1/demo/hearing_salon.csv")
def demo_hearing_csv() -> FileResponse:
    path = SHEET_PATH if SHEET_PATH.exists() else CSV_PATH
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename="hearing-sheet.csv",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v1/demo/last")
def demo_last() -> dict[str, Any]:
    if not LAST_PATH.is_file():
        raise HTTPException(status_code=404, detail="no previous draft")
    return json.loads(LAST_PATH.read_text(encoding="utf-8"))


@router.post("/v1/demo/generate")
async def demo_generate(body: DemoGenerateIn) -> StreamingResponse:
    return await demo_run(body)


@router.post("/v1/demo/run")
async def demo_run(body: DemoGenerateIn) -> StreamingResponse:
    settings = get_settings()
    # Demo mode: keep latency predictable for previews.
    # If the reviewer/model is slow, we still want the UI to complete quickly.
    try:
        settings.request_timeout_sec = min(float(settings.request_timeout_sec), 120.0)
    except Exception:
        settings.request_timeout_sec = 120.0
    hearing = body.to_hearing()
    hearing = _fill_hearing_gaps(hearing)
    if not hearing["business_name"]:
        raise HTTPException(status_code=400, detail="shop name is required")

    async def events():
        started = time.perf_counter()
        job_id = JobStore.new_id()
        now = utcnow()
        rec = JobRecord(
            job_id=job_id,
            job_type="build_site",
            status="running",
            accepted_at=now,
            updated_at=now,
            request={
                "job_type": "build_site",
                "input": {"format": "normalized_json", "data": hearing},
                "options": {"dry_run": not bool(settings.wp_site_url)},
            },
            progress="queued",
        )
        try:
            yield _sse({"type": "stage", "id": "hearing", "hearing": hearing})
            _store.create(rec)
            yield _sse({"type": "stage", "id": "admin"})
            yield _sse({"type": "stage", "id": "job", "job_id": job_id})
            _store.update(job_id, progress="writing")
            registry = ModelRegistry(settings)
            copy = None
            models_used: list[str] = []
            architecture: dict[str, Any] = {}
            estimated_usd = 0.0
            async for kind, payload in run_copy_stack(registry, hearing):
                if kind == "token":
                    yield _sse({"type": "token", "text": payload})
                elif kind == "stage":
                    yield _sse({"type": "stage", **payload})
                elif kind == "done":
                    copy = payload.copy
                    models_used = payload.models_used
                    architecture = payload.architecture
                    estimated_usd = float(payload.estimated_usd or 0.0)
            if copy is None:
                raise RuntimeError("No available primary model")

            latency_ms = int((time.perf_counter() - started) * 1000)
            pending = {
                "copy": copy,
                "hearing": hearing,
                "job_id": job_id,
                "latency_ms": latency_ms,
                "models_used": models_used,
                "architecture": architecture,
                "estimated_usd": estimated_usd,
                "awaiting_review": True,
                "wordpress_started": False,
            }
            LAST_PATH.parent.mkdir(parents=True, exist_ok=True)
            LAST_PATH.write_text(
                json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _store.update(job_id, progress="awaiting_review", result=pending)
            yield _sse({"type": "copy", "copy": copy})
            yield _sse({"type": "stage", "id": "review", "copy": copy})
            yield _sse({"type": "awaiting_review", **pending})
        except (LLMError, ValueError, json.JSONDecodeError) as exc:
            _store.update(job_id, status="failed", error=redact(str(exc)), progress="failed")
            yield _sse({"type": "error", **_friendly(exc), "detail": redact(str(exc))})
        except Exception as exc:  # noqa: BLE001 — demo boundary
            _store.update(job_id, status="failed", error=redact(str(exc)), progress="failed")
            yield _sse({"type": "error", **_friendly(exc), "detail": redact(str(exc))})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class DemoComposeIn(DemoGenerateIn):
    approved_copy: dict[str, Any]
    job_id: str = ""
    decision: str = "approved"


@router.post("/v1/demo/compose")
def demo_compose(body: DemoComposeIn) -> dict[str, Any]:
    if body.decision != "approved":
        raise HTTPException(
            status_code=400, detail="WordPress starts only after the copy is approved"
        )
    hearing = body.to_hearing()
    raw_copy = body.approved_copy or {}
    if not str(raw_copy.get("heading") or "").strip():
        raise HTTPException(status_code=400, detail="approved copy is required")
    copy, validation = prepare_copy_for_wordpress(raw_copy, hearing)
    if validation.get("status") not in WP_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "copy_not_safe_for_wordpress",
                "validation": validation,
            },
        )
    site = compose_site_draft(hearing, copy)
    job_id = body.job_id or JobStore.new_id()
    wp_plan = create_draft_pages(site, job_id=job_id, human_approved=False)
    summary = job_summary(
        hearing, site, latency_ms=0, job_id=job_id, review="approved"
    )
    result = {
        "copy": copy,
        "hearing": hearing,
        "site": site,
        "job_id": job_id,
        "summary": summary,
        "validation": validation,
        "wordpress_payloads": wp_plan.get("payloads") or [],
        "awaiting_review": False,
        "wordpress_started": True,
        "wordpress_live": False,
        "human_approved": False,
        "decision": "approved",
    }
    LAST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if _store.get(job_id):
        _store.update(job_id, status="succeeded", result=result, progress="draft_saved")
    return result


@router.post("/v1/demo/compare")
def demo_compare(body: CompareIn) -> dict[str, Any]:
    """Same hearing + same prompt across models — scored comparison lab."""
    settings = get_settings()
    hearing, meta = _resolve_hearing(body)
    if not hearing.get("business_name"):
        raise HTTPException(status_code=400, detail="business_name is required after CSV normalization")
    registry = ModelRegistry(settings)
    available = {item["id"]: bool(item.get("key_configured")) for item in registry.available()}
    models = [model for model in (body.models or DEFAULT_COMPARE_MODELS) if available.get(model)]
    if not models:
        raise HTTPException(status_code=400, detail="no configured models available for comparison")

    messages = demo_messages(hearing, page=body.page or "top")
    runs: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for model_id in models:
        extra = {"thinking": {"type": "disabled"}} if model_id.startswith("glm-") else {}
        item: dict[str, Any] = {"model": model_id}
        try:
            result = registry.chat(
                model_id,
                messages,
                temperature=0.2,
                max_tokens=2200,
                extra_body=extra,
            )
            copy = parse_copy_json(result.content, hearing=hearing)
            score = score_copy(copy, hearing)
            item.update(
                {
                    "ok": True,
                    "provider": result.provider,
                    "latency_ms": result.latency_ms,
                    "total_tokens": result.usage.total_tokens,
                    "estimated_usd": result.estimated_usd,
                    "score": score,
                    "copy": copy,
                }
            )
        except Exception as exc:  # noqa: BLE001 — comparison boundary
            errors.append({"model": model_id, "error": redact(str(exc))[:800]})
            item.update({"ok": False, "error": redact(str(exc))[:800]})
        runs.append(item)

    ranked = sorted(
        [run for run in runs if run.get("ok")],
        key=lambda run: (
            -(run.get("score") or {}).get("facts_hit", 0),
            len((run.get("score") or {}).get("forbidden_hits") or []),
            (run.get("score") or {}).get("tbd_markers", 99),
            run.get("latency_ms") or 999999,
        ),
    )
    return {
        "hearing": hearing,
        "meta": meta,
        "prompt": "same demo homepage prompt for all models",
        "models_requested": body.models or DEFAULT_COMPARE_MODELS,
        "models_ran": models,
        "runs": runs,
        "errors": errors,
        "recommended": ranked[0]["model"] if ranked else "",
        "ranking": [run["model"] for run in ranked],
    }


@router.post("/v1/demo/hearing/parse")
async def parse_hearing_upload(body: HearingParseIn) -> dict[str, Any]:
    if body.json_data is not None and body.json_data != "":
        payload = body.json_data
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="json object required")
        hearing, meta = _hearing_from_dict(payload)
        source = meta.get("source", "json")
    elif body.csv.strip():
        hearing, meta = _parse_hearing_csv(body.csv)
        source = meta.get("source", "csv")
    else:
        raise HTTPException(status_code=400, detail="csv or json required")
    if not hearing.get("business_name"):
        raise HTTPException(
            status_code=400,
            detail="business_name is required. Fill the shop name in the CSV, then upload again.",
        )
    return {"hearing": hearing, "source": source, "meta": meta, "table": meta.get("table") or build_hearing_tables(hearing)}
