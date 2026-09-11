"""V2 lab API — Type 1–4 hearing production (UI at /ai/v2/)."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ai_agent.api.lab import (
    LabConfigIn,
    REGISTRY,
    _ensure_selected_keys,
    _sse,
    lab_get_config,
    lab_put_config,
    load_lab_config,
    settings_from_lab,
)
from ai_agent.config import get_settings
from ai_agent.models.registry import ModelRegistry
from ai_agent.v2.blueprint import (
    TYPE1_BLUEPRINT_VERSION,
    TYPE2_BLUEPRINT_VERSION,
    TYPE3_BLUEPRINT_VERSION,
    TYPE3_MIN_NAV_PAGES,
    TYPE4_BLUEPRINT_VERSION,
    build_site_blueprint,
    finalize_lab_blueprint,
    inject_missing_type3_nav_pages,
    is_v2_lab_type,
    merge_type3_blueprint_pages,
    refresh_blueprint_stats,
    type3_nav_probe_count,
    uses_satellite_nav,
)
from ai_agent.v2.export import blueprint_to_section_rows, sections_to_csv, sections_to_xlsx_bytes
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.page_catalog import catalog_for_api
from ai_agent.v2.production_types import ProductionType, production_type_label
from ai_agent.v2.pipeline_roles import (
    V2ModelRoleError,
    v2_active_model_ids,
    v2_pipeline_roles,
    v2_planner_model,
    v2_planner_model_ids,
    v2_writer_model,
    validate_v2_model_roles,
)
from ai_agent.v2.prompt_rules import apply_satellite_lab_config, prompt_sections_catalog_v2, resolve_satellite_write_prompts
from ai_agent.v2.section_planner import (
    count_planner_pages,
    enrich_blueprint_with_ai,
    strip_blueprint_section_content,
)
from ai_agent.v2.writer import (
    apply_sections_to_rows,
    blank_section_text,
    fill_empty_shell_sections,
    gemini_inter_page_sleep_sec,
    pages_leave_blank,
    pages_shell_only,
    pages_to_write,
    shell_section_text,
    write_page,
)

router = APIRouter(tags=["lab-v2"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class HearingParseIn(BaseModel):
    csv_text: str = ""


class BlueprintIn(BaseModel):
    hearing: dict[str, Any]
    model_ids: list[str] = Field(default_factory=list)


class BlueprintMergeIn(BaseModel):
    hearing: dict[str, Any]
    blueprint: dict[str, Any] = Field(default_factory=dict)


class ExportIn(BaseModel):
    blueprint: dict[str, Any]
    sections: list[dict[str, str]] | None = None
    format: str = "csv"  # csv | xlsx | both


class WriteIn(BaseModel):
    hearing: dict[str, Any]
    blueprint: dict[str, Any]
    model_ids: list[str] = Field(default_factory=list)
    use_lab_prompt: bool = True
    mode: str = "production"


def _enrich_v2_lab_config(out: dict[str, Any], *, include_catalog: bool = False) -> dict[str, Any]:
    apply_satellite_lab_config(out)
    out["version"] = 2
    out["ui_path"] = "/ai/v2/"
    out["api_prefix"] = "/v2/lab"
    out["blueprint_version"] = TYPE3_BLUEPRINT_VERSION
    out["type1_blueprint_version"] = TYPE1_BLUEPRINT_VERSION
    out["type2_blueprint_version"] = TYPE2_BLUEPRINT_VERSION
    out["type4_blueprint_version"] = TYPE4_BLUEPRINT_VERSION
    out["type3_nav_pages"] = type3_nav_probe_count() or (TYPE3_MIN_NAV_PAGES + 1)
    out["server_nav_probe"] = out["type3_nav_pages"]
    out["satellite_build"] = "2026-09-11-v2-only"
    out["active_production_types"] = ["type1", "type2", "type3", "type4"]
    out["model_roles"] = {
        "semantics": "satellite",
        "max_models": 2,
        "note": "Model #1 = AI-1 dynamic section creator. Model #2 = AI-2 content writer.",
        "1": "AI-1 Section Creator — structure + rules only (never page copy)",
        "2": "AI-2 Content Writer — Japanese text for each section (always model #2)",
    }
    settings = get_settings()
    out["google_client_id"] = str(settings.google_client_id or "").strip()
    out["google_sheets_folder_id"] = str(settings.google_sheets_folder_id or "").strip()
    out["google_sheets"] = {
        "oauthClientConfigured": bool(out["google_client_id"]),
        "folderConfigured": bool(out["google_sheets_folder_id"]),
        "folderName": "BBS-CMS-LAB",
    }
    if include_catalog:
        out["page_catalog"] = catalog_for_api()
        out["production_types"] = [
            {
                "id": ProductionType.TYPE1_SHINKI.value,
                "label": production_type_label(ProductionType.TYPE1_SHINKI),
                "description": "新規 — standard site from hearing (ページの追加 + standard TOP).",
                "status": "active",
            },
            {
                "id": ProductionType.TYPE2_RENEWAL.value,
                "label": production_type_label(ProductionType.TYPE2_RENEWAL),
                "description": "リニューアル — renew existing client site from 既存URL / 既存ページ.",
                "status": "active",
            },
            {
                "id": ProductionType.TYPE3_SATELLITE.value,
                "label": production_type_label(ProductionType.TYPE3_SATELLITE),
                "description": "サテライト — compact branch/landing site + SEO/tag pages.",
                "status": "active",
            },
            {
                "id": ProductionType.TYPE4_SATELLITE_RENEWAL.value,
                "label": production_type_label(ProductionType.TYPE4_SATELLITE_RENEWAL),
                "description": "サテライトリニューアル — satellite template + 既存URL renewal policies.",
                "status": "active",
            },
        ]
        out["export_formats"] = ["csv", "google_sheets"]
        out["ai_stages"] = ["planner", "writer"]
        out["planner_status"] = "llm_type1_type2_type3_type4"
        out["writer_status"] = "active"
    return out


@router.get("/v2/lab/config")
def lab_v2_config() -> dict[str, Any]:
    out = lab_get_config()
    return _enrich_v2_lab_config(out, include_catalog=True)


@router.put("/v2/lab/config")
def lab_v2_put_config(body: LabConfigIn) -> dict[str, Any]:
    out = lab_put_config(body)
    return _enrich_v2_lab_config(out, include_catalog=False)


@router.post("/v2/lab/hearing/parse")
def lab_v2_parse_hearing(body: HearingParseIn) -> dict[str, Any]:
    if not str(body.csv_text or "").strip():
        raise HTTPException(status_code=400, detail="csv_text is required")
    try:
        hearing = parse_hearing_sheet(body.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"hearing": hearing}


def _require_v2_lab_hearing(hearing: dict[str, Any]) -> None:
    if not is_v2_lab_type(hearing):
        raise HTTPException(
            status_code=400,
            detail=(
                "This lab supports Type 1 (新規), Type 2 (リニューアル), "
                "Type 3 (サテライト), and Type 4 (サテライトリニューアル) hearing sheets only"
            ),
        )


async def _build_lab_blueprint(
    *,
    hearing: dict[str, Any],
    model_ids: list[str],
    progress=None,
) -> tuple[dict[str, Any], list[dict[str, str]], str, dict[str, int]]:
    _require_v2_lab_hearing(hearing)
    cfg = load_lab_config()
    try:
        planner, _ = validate_v2_model_roles(model_ids)
    except V2ModelRoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not planner:
        raise HTTPException(
            status_code=400,
            detail="Select at least 1 model (#1 AI-1 Section Creator) in Config before running AI-1.",
        )

    blueprint = build_site_blueprint(hearing)
    if uses_satellite_nav(hearing):
        inject_missing_type3_nav_pages(blueprint, hearing)
    llm_n, total_n = count_planner_pages(blueprint)
    settings = settings_from_lab(cfg)
    registry = ModelRegistry(settings)
    try:
        _ensure_selected_keys(registry, v2_planner_model_ids(model_ids))
    except HTTPException as exc:
        raise HTTPException(status_code=400, detail=str(exc.detail)) from exc

    blueprint = await enrich_blueprint_with_ai(
        registry=registry,
        hearing=hearing,
        blueprint=blueprint,
        planner=planner,
        progress=progress,
    )
    if progress:
        await progress(
            "",
            llm_n,
            max(llm_n, 1),
            "finalize",
            active=[],
            remaining=0,
            llm_done=llm_n,
            llm_total=llm_n,
            template_pages=max(0, total_n - llm_n),
            soft_pct=100.0,
            chars=0,
            chars_total=0,
            expected_chars=0,
        )
    blueprint = finalize_lab_blueprint(blueprint, hearing)
    rows = blueprint_to_section_rows(blueprint)
    stats = {
        "llm_pages": llm_n,
        "total_pages": total_n,
        "csv_rows": len(rows),
        "nav_pages": blueprint.get("stats", {}).get("nav_pages", 0),
    }
    return blueprint, rows, planner, stats


@router.post("/v2/lab/blueprint")
async def lab_v2_blueprint(body: BlueprintIn) -> dict[str, Any]:
    hearing = body.hearing or {}
    _require_v2_lab_hearing(hearing)
    if not str((hearing.get("project") or {}).get("business_name") or "").strip():
        if not str((hearing.get("store") or {}).get("name") or "").strip():
            raise HTTPException(status_code=400, detail="hearing.project.business_name is required")

    cfg = load_lab_config()
    model_ids = body.model_ids or cfg.get("selected_models") or []
    blueprint, rows, planner, stats = await _build_lab_blueprint(hearing=hearing, model_ids=model_ids)
    return {
        "blueprint": blueprint,
        "sections": rows,
        "prompt_sections": prompt_sections_catalog_v2(blueprint),
        "planner": planner,
        "export_preview": {
            "csv_rows": stats["csv_rows"],
            "pages": blueprint.get("stats", {}).get("all_pages", 0),
            "nav_pages": stats["nav_pages"],
            "llm_pages": stats["llm_pages"],
        },
    }


@router.post("/v2/lab/blueprint/stream")
async def lab_v2_blueprint_stream(body: BlueprintIn) -> StreamingResponse:
    hearing = body.hearing or {}
    _require_v2_lab_hearing(hearing)
    if not str((hearing.get("project") or {}).get("business_name") or "").strip():
        if not str((hearing.get("store") or {}).get("name") or "").strip():
            raise HTTPException(status_code=400, detail="hearing.project.business_name is required")

    cfg = load_lab_config()
    model_ids = body.model_ids or cfg.get("selected_models") or []
    try:
        planner, _ = validate_v2_model_roles(model_ids)
    except V2ModelRoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not planner:
        raise HTTPException(
            status_code=400,
            detail="Select at least 1 model (#1 AI-1 Section Creator) in Config before running AI-1.",
        )

    async def events():
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        run_at = datetime.now(UTC).isoformat()

        async def on_progress(slug: str, index: int, total: int, phase: str, **extra: Any) -> None:
            active = extra.get("active") or []
            remaining = extra.get("remaining")
            llm_total = extra.get("llm_total")
            template_pages = extra.get("template_pages")
            section_count = extra.get("section_count") or 0
            soft_pct = extra.get("soft_pct")
            chars = int(extra.get("chars") or 0)
            chars_total = int(extra.get("chars_total") or 0)
            chars_display = int(extra.get("chars_display") or chars_total or 0)
            expected_chars = int(extra.get("expected_chars") or 0)
            # Bar uses AI page planning only (index/total = llm_done/llm_total).
            bar_total = int(llm_total or total or 0) or 1
            bar_index = int(index or 0)
            if phase == "template":
                label = (
                    f"準備完了: テンプレート {template_pages or 0}ページ適用。"
                    f" これからAIが {bar_total}ページの構成を計画します（0/{bar_total}）"
                )
                bar_index = 0
                soft_pct = 0.0
            elif phase == "finalize":
                label = f"確定処理中（AI計画 {bar_index}/{bar_total} 完了）"
                soft_pct = 100.0 if soft_pct is None else soft_pct
            elif phase in ("llm_stream", "llm_wait"):
                running = "、".join(active) if active else (slug or "…")
                label = (
                    f"受信中: {running} · {chars_display:,}文字"
                    f"（完了 {bar_index}/{bar_total} · {soft_pct if soft_pct is not None else 0}%）"
                )
            elif phase == "llm_start":
                running = "、".join(active) if active else slug
                label = f"AI計画中: {running}（完了 {bar_index}/{bar_total}）"
            elif phase == "llm_timeout":
                label = f"タイムアウト: {slug} → テンプレート使用（{bar_index}/{bar_total}）"
            elif slug:
                sec = f" · {section_count}セクション" if section_count else ""
                label = f"AI完了: {slug}{sec}（{bar_index}/{bar_total}）"
            else:
                label = f"AI計画 {bar_index}/{bar_total}"
            if soft_pct is None and bar_total:
                soft_pct = round(100.0 * bar_index / bar_total, 1)
            await q.put(
                {
                    "type": "page",
                    "page": slug,
                    "index": bar_index,
                    "total": bar_total,
                    "phase": phase,
                    "label": label,
                    "active": active,
                    "remaining": remaining if remaining is not None else max(0, bar_total - bar_index),
                    "llm_total": bar_total,
                    "llm_done": bar_index,
                    "template_pages": template_pages,
                    "section_count": section_count,
                    "soft_pct": soft_pct,
                    "chars": chars,
                    "chars_total": chars_total,
                    "chars_display": chars_display,
                    "expected_chars": expected_chars,
                    "progress_kind": "ai_sections",
                    "progress_schema": "ai_chars_v1",
                }
            )

        async def worker() -> None:
            try:
                shell = build_site_blueprint(hearing)
                if uses_satellite_nav(hearing):
                    inject_missing_type3_nav_pages(shell, hearing)
                llm_n, total_n = count_planner_pages(shell)
                await q.put(
                    {
                        "type": "start",
                        "run_at": run_at,
                        "total": llm_n,  # bar = AI pages only
                        "llm_pages": llm_n,
                        "template_pages": max(0, total_n - llm_n),
                        "all_pages": total_n,
                        "label": (
                            f"AI-1開始 — AIが計画するページ {llm_n}件"
                            f"（他 {max(0, total_n - llm_n)}件はテンプレート）"
                        ),
                        "progress_kind": "ai_sections",
                        "progress_schema": "ai_chars_v1",
                    }
                )
                blueprint, rows, planner, stats = await _build_lab_blueprint(
                    hearing=hearing,
                    model_ids=model_ids,
                    progress=on_progress,
                )
                await q.put(
                    {
                        "type": "done",
                        "run_at": run_at,
                        "blueprint": blueprint,
                        "sections": rows,
                        "prompt_sections": prompt_sections_catalog_v2(blueprint),
                        "planner": planner,
                        "export_preview": {
                            "csv_rows": stats["csv_rows"],
                            "nav_pages": stats["nav_pages"],
                            "llm_pages": stats["llm_pages"],
                        },
                    }
                )
            except HTTPException as exc:
                try:
                    from ai_agent.models.quota_tracker import record_failure

                    record_failure(planner, str(exc.detail))
                except Exception:
                    pass
                await q.put({"type": "error", "detail": str(exc.detail)})
            except Exception as exc:  # noqa: BLE001
                try:
                    from ai_agent.models.quota_tracker import record_failure

                    record_failure(planner, str(exc))
                except Exception:
                    pass
                await q.put({"type": "error", "detail": str(exc)})
            finally:
                await q.put(None)

        yield _sse({"type": "hello", "run_at": run_at, "label": "AI-1 接続中…"})
        task = asyncio.create_task(worker())
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=8.0)
                except asyncio.TimeoutError:
                    yield _sse(
                        {
                            "type": "pulse",
                            "label": "モデル応答待ち…（次のページ完了で進捗更新）",
                        }
                    )
                    continue
                if ev is None:
                    break
                yield _sse(ev)
        finally:
            await task

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/v2/lab/blueprint/merge")
def lab_v2_blueprint_merge(body: BlueprintMergeIn) -> dict[str, Any]:
    """Merge AI-1 partial blueprint with full page shell (fixes short nav lists)."""
    hearing = body.hearing or {}
    partial = body.blueprint or {}
    _require_v2_lab_hearing(hearing)
    shell = build_site_blueprint(hearing)
    if uses_satellite_nav(hearing):
        inject_missing_type3_nav_pages(shell, hearing)
    merged = merge_type3_blueprint_pages(partial, shell)
    merged = finalize_lab_blueprint(merged, hearing)
    rows = blueprint_to_section_rows(merged)
    return {
        "blueprint": merged,
        "sections": rows,
        "prompt_sections": prompt_sections_catalog_v2(merged),
        "export_preview": {
            "csv_rows": len(rows),
            "nav_pages": merged.get("stats", {}).get("nav_pages", 0),
        },
    }


@router.post("/v2/lab/write/stream")
async def lab_v2_write_stream(body: WriteIn) -> StreamingResponse:
    hearing = body.hearing or {}
    blueprint = body.blueprint or {}
    _require_v2_lab_hearing(hearing)
    if not blueprint.get("pages"):
        raise HTTPException(status_code=400, detail="blueprint.pages is required — run AI-1 first")

    if uses_satellite_nav(hearing):
        inject_missing_type3_nav_pages(blueprint, hearing)
    blueprint = finalize_lab_blueprint(blueprint, hearing)

    cfg = load_lab_config()
    model_ids = body.model_ids or cfg.get("selected_models") or []
    model_ids = [m for m in model_ids if m in REGISTRY][:2]
    if not model_ids:
        raise HTTPException(status_code=400, detail="no models selected")

    try:
        planner, writer = validate_v2_model_roles(model_ids)
    except V2ModelRoleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _, quality, verifier_pool, pipe_mode = v2_pipeline_roles(model_ids)
    if pipe_mode == "sections_only":
        raise HTTPException(
            status_code=400,
            detail="1 model selected — AI-1 sections only. Add a 2nd model (#2 Content Writer) to run AI-2.",
        )
    if not writer:
        raise HTTPException(status_code=400, detail="Select model #2 as AI-2 Content Writer.")
    if writer != v2_writer_model(model_ids):
        raise HTTPException(status_code=400, detail="AI-2 must use model #2 only.")

    settings = settings_from_lab(cfg)
    registry = ModelRegistry(settings)
    pages = pages_to_write(blueprint)
    shell_pages = pages_shell_only(blueprint)
    blank_pages = pages_leave_blank(blueprint)
    rows = blueprint_to_section_rows(blueprint)
    run_at = datetime.now(UTC).isoformat()
    mode = (body.mode or "production").strip().lower()
    system_prompt, user_template = resolve_satellite_write_prompts(cfg)

    # Fill every site page: blank → shell templates → AI-2 LLM pages
    all_write_pages = list(blank_pages) + list(shell_pages) + list(pages)
    total_write = len(all_write_pages)
    n_instant = len(blank_pages) + len(shell_pages)
    n_ai = len(pages)

    def _write_soft_pct(
        *,
        done_n: int,
        ai_done: int = 0,
        page_frac: float = 0.0,
        phase: str = "instant",
    ) -> float:
        """Progress bar that does not stick at ~8% on page 1 of a large site.

        Instant shell/blank pages take a small share of the bar; AI pages drive the rest
        so each LLM page can advance ~ (95/n_ai)% instead of ~(100/total_write)%.
        """
        if total_write <= 0:
            return 0.0
        if n_ai <= 0:
            return round(min(100.0, 100.0 * done_n / total_write), 1)
        instant_share = min(12.0, 100.0 * n_instant / max(total_write, 1)) if n_instant else 0.0
        ai_share = 100.0 - instant_share
        if phase == "instant":
            if n_instant <= 0:
                return 0.0
            return round(instant_share * (done_n / n_instant), 1)
        # AI phase — all instant pages already finished.
        frac = min(0.95, max(0.0, float(page_frac)))
        return round(min(99.5, instant_share + ai_share * ((ai_done + frac) / n_ai)), 1)

    def _page_frac(elapsed: float, chars: int) -> float:
        """Blend elapsed time + streamed chars so the bar moves while tokens arrive."""
        pace = 90.0 if str(writer).startswith("gemini") else 40.0
        expected_chars = 2200.0
        time_frac = elapsed / pace if pace > 0 else 0.0
        char_frac = (chars / expected_chars) if expected_chars > 0 else 0.0
        return min(0.95, max(time_frac * 0.75, char_frac * 0.9, (time_frac + char_frac) * 0.45))

    async def events():
        yield _sse(
            {
                "type": "start",
                "run_at": run_at,
                "writer": writer,
                "planner": planner,
                "quality_writer": quality,
                "verifiers": verifier_pool,
                "pages": [p.get("slug") for p in all_write_pages],
                "total": total_write,
                "ai_pages": n_ai,
                "shell_pages": len(shell_pages),
                "soft_pct": 0.0,
                "label": (
                    f"AI-2開始 — 本文 {total_write}ページ"
                    f"（AI {n_ai} + シェル {len(shell_pages)}）"
                ),
            }
        )
        started = time.perf_counter()
        current_slug = ""
        done_n = 0
        ai_done = 0
        try:
            _ensure_selected_keys(registry, v2_active_model_ids(model_ids))
            for page in blank_pages:
                slug = str(page.get("slug") or page.get("id") or "page")
                current_slug = slug
                label = str(page.get("nav_label") or slug)
                yield _sse(
                    {
                        "type": "stage",
                        "id": f"blank_{slug}",
                        "label": f"空白ページ処理中: {label}",
                        "page": slug,
                        "index": done_n,
                        "total": total_write,
                        "soft_pct": _write_soft_pct(done_n=done_n, phase="instant"),
                    }
                )
                section_text = blank_section_text(page)
                apply_sections_to_rows(rows, page_slug=slug, section_text=section_text)
                done_n += 1
                yield _sse(
                    {
                        "type": "page_done",
                        "page": slug,
                        "nav_label": label,
                        "sections": section_text,
                        "models_used": [],
                        "blank": True,
                        "index": done_n,
                        "total": total_write,
                        "soft_pct": _write_soft_pct(done_n=done_n, phase="instant"),
                        "label": f"完了（空白）: {label}（{done_n}/{total_write}）",
                    }
                )
            for page in shell_pages:
                slug = str(page.get("slug") or page.get("id") or "page")
                current_slug = slug
                label = str(page.get("nav_label") or slug)
                yield _sse(
                    {
                        "type": "stage",
                        "id": f"shell_{slug}",
                        "label": f"シェル本文: {label}（{done_n + 1}/{total_write}）",
                        "page": slug,
                        "index": done_n,
                        "total": total_write,
                        "soft_pct": _write_soft_pct(done_n=done_n, phase="instant"),
                    }
                )
                section_text = shell_section_text(page, hearing)
                apply_sections_to_rows(rows, page_slug=slug, section_text=section_text)
                done_n += 1
                yield _sse(
                    {
                        "type": "page_done",
                        "page": slug,
                        "nav_label": label,
                        "sections": section_text,
                        "models_used": [],
                        "shell": True,
                        "index": done_n,
                        "total": total_write,
                        "soft_pct": _write_soft_pct(done_n=done_n, phase="instant"),
                        "label": f"完了（シェル）: {label}（{done_n}/{total_write}）",
                    }
                )
            for page in pages:
                slug = str(page.get("slug") or page.get("id") or "page")
                current_slug = slug
                label = str(page.get("nav_label") or slug)
                yield _sse(
                    {
                        "type": "stage",
                        "id": f"write_{slug}",
                        "label": f"本文作成中: {label}（{done_n + 1}/{total_write}）",
                        "page": slug,
                        "index": done_n,
                        "total": total_write,
                        "ai_pages": n_ai,
                        "ai_done": ai_done,
                        "soft_pct": _write_soft_pct(
                            done_n=done_n, ai_done=ai_done, page_frac=0.0, phase="ai"
                        ),
                    }
                )
                page_chars = {"n": 0}
                page_t0 = time.perf_counter()

                async def _on_chars(n: int, _pc=page_chars) -> None:
                    _pc["n"] = int(n or 0)

                write_task = asyncio.create_task(
                    write_page(
                        registry=registry,
                        hearing_v2=hearing,
                        page=page,
                        writer=writer,
                        quality=quality,
                        verifier_pool=verifier_pool,
                        system_prompt=system_prompt,
                        user_template=user_template,
                        mode=mode,
                        on_chars=_on_chars,
                    )
                )
                while not write_task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(write_task), timeout=0.8)
                    except asyncio.TimeoutError:
                        elapsed = time.perf_counter() - page_t0
                        page_frac = _page_frac(elapsed, page_chars["n"])
                        soft = _write_soft_pct(
                            done_n=done_n,
                            ai_done=ai_done,
                            page_frac=page_frac,
                            phase="ai",
                        )
                        yield _sse(
                            {
                                "type": "heartbeat",
                                "page": slug,
                                "nav_label": label,
                                "index": done_n,
                                "total": total_write,
                                "ai_pages": n_ai,
                                "ai_done": ai_done,
                                "chars": page_chars["n"],
                                "elapsed_sec": round(elapsed, 1),
                                "soft_pct": soft,
                                "label": (
                                    f"本文作成中: {label}（{done_n + 1}/{total_write}）"
                                    f" · 受信 {page_chars['n']}文字 · {int(elapsed)}s"
                                ),
                            }
                        )
                stack, section_text = write_task.result()
                section_text = fill_empty_shell_sections(page, section_text, hearing)
                apply_sections_to_rows(rows, page_slug=slug, section_text=section_text)
                done_n += 1
                ai_done += 1
                yield _sse(
                    {
                        "type": "page_done",
                        "page": slug,
                        "nav_label": label,
                        "sections": section_text,
                        "models_used": stack.models_used if hasattr(stack, "models_used") else [],
                        "index": done_n,
                        "total": total_write,
                        "ai_pages": n_ai,
                        "ai_done": ai_done,
                        "soft_pct": _write_soft_pct(
                            done_n=done_n, ai_done=ai_done, page_frac=0.0, phase="ai"
                        ),
                        "label": f"完了: {label}（{done_n}/{total_write}）",
                    }
                )
                # Pace Gemini free-tier RPM; keep SSE alive so nginx/browser
                # do not drop the stream as a "network error".
                pace = gemini_inter_page_sleep_sec(writer)
                if pace > 0:
                    paced = 0.0
                    while paced < pace:
                        step = min(1.0, pace - paced)
                        await asyncio.sleep(step)
                        paced += step
                        yield _sse(
                            {
                                "type": "heartbeat",
                                "page": "",
                                "index": done_n,
                                "total": total_write,
                                "ai_pages": n_ai,
                                "ai_done": ai_done,
                                "soft_pct": _write_soft_pct(
                                    done_n=done_n,
                                    ai_done=ai_done,
                                    page_frac=0.0,
                                    phase="ai",
                                ),
                                "label": (
                                    f"次ページ待機… {paced:.0f}/{pace:.0f}s"
                                    f"（AI本文 {ai_done}/{n_ai}）"
                                ),
                            }
                        )
            speed = round((time.perf_counter() - started) * 1000) / 1000
            blueprint_out = dict(blueprint)
            blueprint_out["ai_stages"] = {
                "planner": "complete",
                "writer": "complete",
                "planner_model": planner,
                "content_model": writer,
            }
            from ai_agent.v2.blueprint import refresh_blueprint_stats

            refresh_blueprint_stats(blueprint_out)
            yield _sse(
                {
                    "type": "done",
                    "speed_sec": speed,
                    "sections": rows,
                    "blueprint": blueprint_out,
                    "writer": writer,
                    "soft_pct": 100.0,
                    "index": total_write,
                    "total": total_write,
                    "ai_pages": n_ai,
                    "ai_done": ai_done,
                }
            )
        except Exception as exc:  # noqa: BLE001
            try:
                from ai_agent.models.quota_tracker import record_failure

                # Only mark quota chips for real 429/quota — not network drops.
                record_failure(writer, str(exc))
            except Exception:
                pass
            yield _sse(
                {
                    "type": "error",
                    "detail": str(exc),
                    "page": current_slug or None,
                    "partial": True,
                    "index": done_n,
                    "total": total_write,
                    "ai_pages": n_ai,
                    "ai_done": ai_done,
                    "sections": rows,
                    "soft_pct": _write_soft_pct(
                        done_n=done_n,
                        ai_done=ai_done,
                        page_frac=0.0,
                        phase="ai" if n_ai else "instant",
                    ),
                    "label": (
                        f"中断: AI本文 {ai_done}/{n_ai} ページ完了"
                        f"（全体 {done_n}/{total_write}）"
                    ),
                }
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/v2/lab/export")
def lab_v2_export(body: ExportIn) -> dict[str, Any]:
    blueprint = body.blueprint or {}
    rows = body.sections if body.sections is not None else blueprint_to_section_rows(blueprint)
    fmt = (body.format or "csv").strip().lower()
    out: dict[str, Any] = {"rows": len(rows)}
    if fmt in {"csv", "both"}:
        out["csv"] = sections_to_csv(rows)
    if fmt in {"xlsx", "both"}:
        out["xlsx_base64"] = None
        try:
            import base64

            raw = sections_to_xlsx_bytes(rows, blueprint=blueprint)
            out["xlsx_base64"] = base64.b64encode(raw).decode("ascii")
        except RuntimeError as exc:
            out["xlsx_error"] = str(exc)
    return out


@router.post("/v2/lab/export/xlsx")
def lab_v2_export_xlsx(body: ExportIn) -> Response:
    blueprint = body.blueprint or {}
    rows = body.sections if body.sections is not None else blueprint_to_section_rows(blueprint)
    try:
        data = sections_to_xlsx_bytes(rows, blueprint=blueprint)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    name = str(blueprint.get("site_name") or "site").replace("/", "-")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}-sections.xlsx"'},
    )
