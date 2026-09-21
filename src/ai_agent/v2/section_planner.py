"""AI-1: LLM section planner — dynamic section blocks per page from hearing."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from ai_agent.models.registry import ModelRegistry
from ai_agent.models.types import ChatMessage
from ai_agent.pipeline.ai_stack import extra_body_for, writer_max_tokens_for
from ai_agent.v2.blueprint import refresh_blueprint_stats
from ai_agent.v2.hearing_writer_adapter import v2_hearing_to_production
from ai_agent.v2.page_catalog import sections_for_page_type
from ai_agent.v2.prompt_packs import default_ai1_planner_for_type
from ai_agent.v2.section_rules import enrich_page_sections

VALID_MODES = frozenset({"generate", "facts", "expand", "shell", "blank"})

# Fallback only — lab should pass the per-type English AI-1 pack.
PLANNER_SYSTEM = default_ai1_planner_for_type("type3")

FORBIDDEN_SECTION_KEYS = frozenset({"text", "content", "body", "copy", "html", "paragraphs", "body_paragraphs"})
MAX_RULE_LEN = 400
PLANNER_CONCURRENCY = 3
PLANNER_PAGE_TIMEOUT_SEC = 35.0
# Typical AI-1 JSON size for one page (used for smooth % while streaming).
PLANNER_EXPECTED_CHARS = 650
PLANNER_STREAM_EMIT_CHARS = 28
PLANNER_STREAM_EMIT_SEC = 0.2
SHELL_PAGE_TYPES = frozenset({"blog", "sitemap", "privacy", "column", "seo", "tag", "news", "ai_blog"})
SHELL_ROLES = frozenset({"shell"})

ProgressCallback = Any  # async (slug, index, total, phase, **extra) -> None
CharDeltaCallback = Any  # async (chars: int) -> None


def page_needs_llm_planner(page: dict[str, Any], *, page_group: str) -> bool:
    """Nav content pages use LLM; SEO/tag/shell/blank use deterministic templates."""
    if not isinstance(page, dict):
        return False
    if page.get("leave_blank"):
        return False
    if page_group in ("seo", "tag"):
        return False
    if str(page.get("role") or "") in SHELL_ROLES:
        return False
    if str(page.get("type") or "") in SHELL_PAGE_TYPES:
        return False
    return True


def count_planner_pages(blueprint: dict[str, Any]) -> tuple[int, int]:
    """Return (llm_page_count, total_page_count)."""
    llm = 0
    total = 0
    for key, group in (("pages", "nav"), ("seo_pages", "seo"), ("tag_pages", "tag")):
        for page in blueprint.get(key) or []:
            if not isinstance(page, dict):
                continue
            total += 1
            if page_needs_llm_planner(page, page_group=group):
                llm += 1
    return llm, total


def _apply_template_sections(page: dict[str, Any], hearing: dict[str, Any]) -> None:
    page["sections_source"] = "template"
    enrich_page_sections(page, hearing)


def _compact_hearing_for_planner(hearing: dict[str, Any]) -> dict[str, Any]:
    """Compact hearing facts for AI-1 — include page composition ② flags + page-add slots."""
    prod = v2_hearing_to_production(hearing)
    keys = (
        "business_name",
        "area",
        "address",
        "phone",
        "concept",
        "hours",
        "closed",
        "focus_keywords",
        "tag_keywords",
        "services",
        "menu",
        "writing_guidance",
        "selling_points",
        "cv_destination",
        "reference_sites",
        "page_directives",
        "tone",
        "target",
        "faq_items",
        "reviews",
        "recruit",
        "ai_blog",
        "production_kind",
        "ai_support",
        "existing_site_copy",
        "existing_url",
    )
    compact: dict[str, Any] = {}
    for key in keys:
        val = prod.get(key)
        if val:
            compact[key] = val
    flags = hearing.get("flags") if isinstance(hearing.get("flags"), dict) else {}
    compact["flags"] = {
        "include_reviews": bool(flags.get("include_reviews")),
        "include_recruit": bool(flags.get("include_recruit")),
        "include_ai_blog": bool(flags.get("include_ai_blog")),
        "blog": bool(flags.get("blog")),
        "access_page": bool(flags.get("access_page")),
        "form": bool(flags.get("form")),
        "top_inherit": bool(flags.get("top_inherit")),
    }
    # Page-add slots (page composition ③) — type + seeds only
    page_slots = []
    for slot in hearing.get("pages") or []:
        if not isinstance(slot, dict):
            continue
        page_slots.append(
            {
                "type": slot.get("type"),
                "items": (slot.get("items") or [])[:8],
            }
        )
    if page_slots:
        compact["page_add_slots"] = page_slots[:20]
    if hearing.get("reviews"):
        compact["reviews"] = hearing.get("reviews")
    if hearing.get("recruit"):
        compact["recruit"] = hearing.get("recruit")
    if hearing.get("ai_blog"):
        compact["ai_blog"] = hearing.get("ai_blog")
    project = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    if project.get("production_kind"):
        compact["production_kind"] = project.get("production_kind")
    if project.get("purpose"):
        compact["site_purpose"] = project.get("purpose")
    if project.get("domain"):
        compact["public_domain"] = project.get("domain")
    if project.get("site_category") or hearing.get("site_category"):
        compact["site_category"] = project.get("site_category") or hearing.get("site_category")
    if project.get("industry") or project.get("industry_category"):
        compact["industry"] = project.get("industry") or project.get("industry_category")
    if project.get("ai_support"):
        compact["ai_support"] = project.get("ai_support")
    if project.get("existing_site_copy"):
        compact["existing_site_copy"] = project.get("existing_site_copy")
    if project.get("existing_url"):
        compact["existing_url"] = project.get("existing_url")
    brief = hearing.get("site_brief") if isinstance(hearing.get("site_brief"), dict) else project.get("site_brief")
    if isinstance(brief, dict) and brief:
        compact["site_brief"] = {
            k: brief.get(k)
            for k in ("category", "purpose", "production_kind", "audience", "goal", "domain")
            if brief.get(k)
        }
        cat = str(brief.get("category") or compact.get("site_category") or "")
        if cat:
            from ai_agent.v2.category_guard import category_playbook_lines

            compact["category_playbook"] = category_playbook_lines(cat)
    note = str(hearing.get("top_inherit_note") or "").strip()
    if note:
        compact["top_inherit_note"] = note
    live = hearing.get("live_site_analysis") if isinstance(hearing.get("live_site_analysis"), dict) else None
    if live and live.get("ok"):
        compact["live_site_structure"] = {
            "nav": (live.get("nav_union") or [])[:12],
            "policy": live.get("policy") or {"copy": "forbidden"},
            "note": "Use for section/item structure only. Never copy live body text. Hearing facts win.",
        }
    return compact


def _loads_planner_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("AI-1 returned empty response")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI-1 output is not JSON")
    blob = text[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*}", "}", blob)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        return json.loads(cleaned)


def _normalize_section(row: dict[str, Any], *, page: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    sid = re.sub(r"[^a-z0-9_]", "_", str(row.get("id") or "").strip().lower()).strip("_")
    if not sid or len(sid) > 32:
        return None
    mode = str(row.get("mode") or "generate").strip().lower()
    if mode not in VALID_MODES:
        mode = "generate"
    if page.get("leave_blank"):
        mode = "blank"
    label = str(row.get("label") or sid).strip() or sid
    rule = str(row.get("rule") or "").strip()
    # AI-1 must not pass through content fields — only planning metadata.
    for bad in FORBIDDEN_SECTION_KEYS:
        if bad in row and str(row.get(bad) or "").strip():
            raise ValueError(f"AI-1 must not output section {bad} — content is AI-2 only")
    if page.get("leave_blank"):
        rule = str(page.get("leave_blank_reason") or "ヒアリング指示: 全セクション空文字") + " " + rule
    if len(rule) > MAX_RULE_LEN:
        rule = rule[:MAX_RULE_LEN].rstrip() + "…"
    return {"id": sid, "label": label, "rule": rule, "mode": mode}


def _is_forbidden_extra_section(section_id: str, page_type: str) -> bool:
    """Drop AI-1 invented SEO/tag slots on non SEO/tag pages (e.g. concept seo_intro_*)."""
    sid = str(section_id or "").strip().lower()
    ptype = str(page_type or "").strip()
    if ptype in {"seo", "tag"}:
        return False
    if sid.startswith("seo_") or sid.startswith("tag_"):
        return True
    if sid in {"brand_origin", "aftercare_philosophy", "one_stop_service", "lead_concept"}:
        return True
    # Layout-word invent ids (hero = layout, not structure)
    if sid == "hero" or sid.startswith("hero_"):
        return True
    # Legacy flat TOP slots replaced by nested top_catchphrase / business_info / cta
    if sid.startswith("business_info_") or sid in {
        "hero_brand_name",
        "hero_catchcopy",
        "hero_subcopy",
        "hero_focus_keywords",
        "hero_cta_label",
        "hero_cta_url",
        "lead_heading",
        "lead_body",
        "services_teaser_heading",
        "services_teaser_items",
        "selling_points_heading",
        "selling_points_points",
        "cta_label",
        "cta_phone",
        "cta_url",
        "cta_line_url",
        "cta_methods",
    }:
        return True
    # Legacy flat invent names replaced by nested concept/service items.
    if sid in {"points", "service_list"} and ptype in {
        "コンセプト",
        "concept",
        "サービス",
        "service",
    }:
        return True
    return False


def finalize_planned_sections(
    planned: list[dict[str, str]],
    page: dict[str, Any],
    *,
    hearing: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Keep catalog slots (facts modes), drop invented extras, preserve allowed AI-1 adds."""
    ptype = str(page.get("type") or "").strip()
    # Prefer blueprint sections already expanded from THIS hearing (same output every run).
    existing = [dict(s) for s in (page.get("sections") or []) if isinstance(s, dict) and s.get("id")]
    if existing:
        catalog = existing
    else:
        catalog = sections_for_page_type(ptype, page=page, hearing=hearing)
    filtered = [
        dict(s)
        for s in planned
        if isinstance(s, dict) and s.get("id") and not _is_forbidden_extra_section(str(s["id"]), ptype)
    ]
    by_id = {str(s["id"]): s for s in filtered}
    out: list[dict[str, str]] = []
    for cat in catalog:
        sid = str(cat.get("id") or "")
        if not sid:
            continue
        if sid in by_id:
            sec = dict(by_id.pop(sid))
            # Catalog facts/shell/blank modes win so AI-1 cannot blank a known fact slot.
            cat_mode = str(cat.get("mode") or "").strip()
            if cat_mode in {"facts", "shell", "blank"}:
                sec["mode"] = cat_mode
            if cat_mode == "facts" and not str(sec.get("rule") or "").strip():
                sec["rule"] = str(cat.get("rule") or "")
            if cat.get("fields") and not sec.get("fields"):
                sec["fields"] = list(cat["fields"])
            # Keep catalog label/rule shape when AI-1 omits nested fields metadata.
            if cat.get("label") and not str(sec.get("label") or "").strip():
                sec["label"] = str(cat.get("label") or sid)
            out.append(sec)
        else:
            row = {
                "id": sid,
                "label": str(cat.get("label") or sid),
                "mode": str(cat.get("mode") or "generate"),
                "rule": str(cat.get("rule") or ""),
            }
            if cat.get("fields"):
                row["fields"] = list(cat["fields"])
            out.append(row)
    for sid, sec in by_id.items():
        out.append(sec)
    return out


def parse_planner_sections(content: str, *, page: dict[str, Any]) -> list[dict[str, str]]:
    data = _loads_planner_json(content)
    raw_sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(raw_sections, list):
        raise ValueError("AI-1 JSON missing sections array")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in raw_sections:
        sec = _normalize_section(row, page=page)
        if not sec or sec["id"] in seen:
            continue
        seen.add(sec["id"])
        out.append(sec)
    if page.get("leave_blank") and not out:
        out.append(
            {
                "id": "placeholder",
                "label": "Blank page",
                "mode": "blank",
                "rule": str(page.get("leave_blank_reason") or "空白ページ"),
            }
        )
    if not out:
        raise ValueError("AI-1 returned no valid sections")
    return finalize_planned_sections(out, page)


def _page_context_block(page: dict[str, Any], hearing: dict[str, Any]) -> str:
    lines = [
        f"page_slug: {page.get('slug')}",
        f"page_type: {page.get('type')}",
        f"nav_label: {page.get('nav_label')}",
        f"role: {page.get('role')}",
    ]
    seeds = page.get("content_seeds") or []
    if seeds:
        lines.append("content_seeds: " + " | ".join(str(s) for s in seeds))
    if page.get("leave_blank"):
        lines.append("leave_blank: true — output blank mode sections only")
    if page.get("reference_url"):
        lines.append(f"reference_url: {page.get('reference_url')}")
    live = page.get("live_structure") if isinstance(page.get("live_structure"), dict) else None
    if live:
        lines.append(
            "live_site_structure (hint only — do NOT copy live body text; hearing facts win): "
            + json.dumps(
                {
                    "pattern": live.get("pattern"),
                    "suggested_point_count": live.get("suggested_point_count"),
                    "suggested_faq_count": live.get("suggested_faq_count"),
                    "section_headings": (live.get("section_headings") or [])[:6],
                    "point_title_hints": (live.get("point_title_hints") or [])[:5],
                    "faq_question_headings": (live.get("faq_question_headings") or [])[:5],
                },
                ensure_ascii=False,
            )[:900]
        )
    if page.get("live_topic_hints"):
        lines.append(
            "live_topic_hints (rewrite from hearing only): "
            + " | ".join(str(x)[:60] for x in (page.get("live_topic_hints") or [])[:6])
        )
    if page.get("seo_overview"):
        lines.append(f"seo_overview: {page.get('seo_overview')}")
    if page.get("tag_instruction"):
        lines.append(f"tag_instruction: {page.get('tag_instruction')}")
    if page.get("tag_body"):
        lines.append(f"tag_body: {page.get('tag_body')}")
    seo = page.get("seo_sections")
    if isinstance(seo, dict) and seo:
        lines.append("seo_section_hints: " + json.dumps(seo, ensure_ascii=False)[:800])
    wg = hearing.get("writing_guidance") or {}
    for key in ("writing_notes", "remarks", "selling_points", "atmosphere", "ng_tone"):
        val = str(wg.get(key) or "").strip()
        if val:
            lines.append(f"{key}: {val[:300]}")
    template = page.get("sections") or []
    if template:
        from ai_agent.v2.page_catalog import nested_fields_for_section

        lines.append(
            "template_hint_ids (REQUIRED — include every id; do not invent seo_/brand_origin/hero ids):"
        )
        for sec in template:
            if not isinstance(sec, dict):
                continue
            sid = str(sec.get("id") or "").strip()
            if not sid:
                continue
            mode = str(sec.get("mode") or "generate")
            fields = nested_fields_for_section(sec)
            if fields:
                shape = "{" + ",".join(fields) + "}"
                lines.append(f"  - {sid} ({mode}) nested={shape}")
            else:
                lines.append(f"  - {sid} ({mode}) string")
        lines.append(
            "Plan these section ids for THIS page. Use the nested shapes listed above."
        )
    return "\n".join(lines)


def _planner_messages(
    hearing: dict[str, Any],
    page: dict[str, Any],
    *,
    system_prompt: str | None = None,
) -> list[ChatMessage]:
    compact = _compact_hearing_for_planner(hearing)
    ptype = str(hearing.get("production_type") or "").strip() or "unknown"
    user = (
        f"Plan section blocks for this WordPress page from THIS hearing sheet only.\n"
        f"Hearing production_type: {ptype}\n"
        f"Do not invent facts. Output id, label, mode, rule only — no page copy.\n"
        f"Type rules are already in the system prompt.\n\n"
        "=== PAGE ===\n"
        + _page_context_block(page, hearing)
        + "\n\n=== HEARING FACTS (compact) ===\n"
        + json.dumps(compact, ensure_ascii=False, indent=2)
        + '\n\nReturn JSON only (structure — NO page copy): '
        '{"sections": [{"id":"...","label":"...","mode":"...","rule":"short English instruction for AI-2 from hearing facts"}]}'
    )
    system = (system_prompt or "").strip() or PLANNER_SYSTEM
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]


async def _stream_planner_raw(
    *,
    registry: ModelRegistry,
    planner: str,
    messages: list[ChatMessage],
    max_tokens: int,
    chat_kwargs: dict[str, Any],
    on_chars: CharDeltaCallback | None = None,
) -> str:
    """Stream model tokens and report cumulative character count."""
    parts: list[str] = []
    chars = 0
    async for token in registry.chat_stream(
        planner,
        messages,
        temperature=0.3,
        max_tokens=max_tokens,
        **chat_kwargs,
    ):
        text = str(token or "")
        if not text:
            continue
        parts.append(text)
        chars += len(text)
        if on_chars:
            await on_chars(chars)
    raw = "".join(parts).strip()
    if raw:
        return raw
    # Some providers only support non-stream; fall back once.
    result = await asyncio.to_thread(
        registry.chat,
        planner,
        messages,
        temperature=0.3,
        max_tokens=max_tokens,
        **chat_kwargs,
    )
    raw = (result.content or "").strip()
    if on_chars and raw:
        await on_chars(len(raw))
    return raw


async def plan_page_sections(
    *,
    registry: ModelRegistry,
    planner: str,
    hearing: dict[str, Any],
    page: dict[str, Any],
    on_chars: CharDeltaCallback | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    messages = _planner_messages(hearing, page, system_prompt=system_prompt)
    max_tokens = min(writer_max_tokens_for(planner), 4096)
    chat_kwargs: dict[str, Any] = {}
    extra = dict(extra_body_for(planner) or {})
    mid = str(planner or "").lower()
    if mid.startswith("gemini") or "gemini" in mid:
        extra["response_format"] = {"type": "json_object"}
    if extra:
        chat_kwargs["extra_body"] = extra

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = await _stream_planner_raw(
                registry=registry,
                planner=planner,
                messages=messages,
                max_tokens=max_tokens,
                chat_kwargs=chat_kwargs,
                on_chars=on_chars,
            )
        except Exception:
            if chat_kwargs.get("extra_body") and attempt == 0:
                body = dict(chat_kwargs.get("extra_body") or {})
                if "response_format" in body:
                    body.pop("response_format", None)
                    if body:
                        chat_kwargs["extra_body"] = body
                    else:
                        chat_kwargs.pop("extra_body", None)
                    continue
                chat_kwargs.pop("extra_body", None)
                continue
            raise
        try:
            return parse_planner_sections(raw, page=page)
        except ValueError as exc:
            last_error = exc
            if attempt == 0 and raw:
                messages = list(messages) + [
                    ChatMessage(role="assistant", content=raw[:3000]),
                    ChatMessage(
                        role="user",
                        content='Fix JSON. Return only: {"sections": [{"id":"top_catchphrase","label":"TOP catchphrase","mode":"generate","rule":"..."}]}',
                    ),
                ]
                continue
            slug = str(page.get("slug") or "page")
            raise ValueError(f"AI-1 {slug}: {exc}") from exc
    if last_error:
        raise last_error
    raise RuntimeError("AI-1 section planning failed")


async def enrich_blueprint_with_ai(
    *,
    registry: ModelRegistry,
    hearing: dict[str, Any],
    blueprint: dict[str, Any],
    planner: str,
    progress: ProgressCallback | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Replace template sections with AI-1 planned sections (parallel LLM for nav content pages)."""
    llm_jobs: list[tuple[dict[str, Any], str]] = []
    template_count = 0
    planner_system = (system_prompt or "").strip() or PLANNER_SYSTEM

    for key, group in (("pages", "nav"), ("seo_pages", "seo"), ("tag_pages", "tag")):
        for page in blueprint.get(key) or []:
            if not isinstance(page, dict):
                continue
            if page_needs_llm_planner(page, page_group=group):
                llm_jobs.append((page, group))
            else:
                _apply_template_sections(page, hearing)
                template_count += 1

    total_llm = len(llm_jobs)
    if progress:
        await progress(
            "",
            0,
            max(total_llm, 1),
            "template",
            active=[],
            remaining=total_llm,
            llm_done=0,
            llm_total=total_llm,
            template_pages=template_count,
            soft_pct=0.0,
            chars=0,
            chars_total=0,
            expected_chars=PLANNER_EXPECTED_CHARS * max(total_llm, 1),
        )

    sem = asyncio.Semaphore(PLANNER_CONCURRENCY)
    llm_done = 0
    llm_lock = asyncio.Lock()
    active: set[str] = set()
    page_chars: dict[str, int] = {}
    page_started: dict[str, float] = {}
    finished_chars = 0
    last_stream_emit = 0.0
    stop_ticker = asyncio.Event()

    def soft_units() -> float:
        units = float(llm_done)
        now = time.monotonic()
        for slug in active:
            c = float(page_chars.get(slug, 0))
            char_part = min(0.72, c / PLANNER_EXPECTED_CHARS)
            # While waiting for tokens (rate-limit / TTFT), creep like a char counter.
            started = page_started.get(slug, now)
            time_part = min(0.28, (now - started) / PLANNER_PAGE_TIMEOUT_SEC * 0.28)
            units += 0.04 + max(char_part, time_part)
        return units

    def soft_pct() -> float:
        if total_llm <= 0:
            return 100.0
        return round(min(99.0, 100.0 * soft_units() / total_llm), 1)

    def chars_total() -> int:
        return finished_chars + sum(page_chars.get(s, 0) for s in active)

    def est_chars_display() -> int:
        """Blend real streamed chars with time-based estimate while waiting."""
        now = time.monotonic()
        total = finished_chars
        for slug in active:
            real = page_chars.get(slug, 0)
            if real > 0:
                total += real
                continue
            started = page_started.get(slug, now)
            # ~18 chars/sec estimated while waiting — pure UX meter, not billed tokens.
            total += int(min(PLANNER_EXPECTED_CHARS * 0.85, (now - started) * 18))
        return total

    async def emit(
        slug: str,
        phase: str,
        *,
        section_count: int = 0,
        force: bool = False,
    ) -> None:
        nonlocal last_stream_emit
        if not progress:
            return
        now = time.monotonic()
        if phase in ("llm_stream", "llm_wait") and not force:
            if now - last_stream_emit < PLANNER_STREAM_EMIT_SEC:
                return
        last_stream_emit = now
        await progress(
            slug,
            llm_done,
            max(total_llm, 1),
            phase,
            active=sorted(active),
            remaining=max(0, total_llm - llm_done),
            llm_done=llm_done,
            llm_total=total_llm,
            template_pages=template_count,
            section_count=section_count,
            soft_pct=soft_pct(),
            chars=page_chars.get(slug, 0) if slug else 0,
            chars_total=chars_total(),
            chars_display=est_chars_display(),
            expected_chars=PLANNER_EXPECTED_CHARS * max(total_llm, 1),
        )

    async def progress_ticker() -> None:
        """Keep the bar moving every ~0.35s while LLM pages are in flight."""
        while not stop_ticker.is_set():
            try:
                await asyncio.wait_for(stop_ticker.wait(), timeout=0.35)
                return
            except asyncio.TimeoutError:
                if active:
                    await emit("", "llm_wait")

    async def plan_one(page: dict[str, Any]) -> None:
        nonlocal llm_done, finished_chars
        slug = str(page.get("slug") or page.get("id") or "page")
        async with sem:
            async with llm_lock:
                active.add(slug)
                page_chars[slug] = 0
                page_started[slug] = time.monotonic()
            await emit(slug, "llm_start", force=True)
            status = "ok"
            section_count = 0
            last_chars_emitted = 0

            async def on_chars(n: int) -> None:
                nonlocal last_chars_emitted
                async with llm_lock:
                    page_chars[slug] = n
                if n - last_chars_emitted >= PLANNER_STREAM_EMIT_CHARS or n < last_chars_emitted:
                    last_chars_emitted = n
                    await emit(slug, "llm_stream")

            try:
                sections = await asyncio.wait_for(
                    plan_page_sections(
                        registry=registry,
                        planner=planner,
                        hearing=hearing,
                        page=page,
                        on_chars=on_chars,
                        system_prompt=planner_system,
                    ),
                    timeout=PLANNER_PAGE_TIMEOUT_SEC,
                )
                page["sections"] = sections
                page["sections_source"] = "ai-1"
                enrich_page_sections(page, hearing)
                section_count = len(page.get("sections") or [])
            except asyncio.TimeoutError:
                status = "timeout"
                page["sections_source"] = "template_fallback"
                page["planner_timeout"] = True
                enrich_page_sections(page, hearing)
                section_count = len(page.get("sections") or [])
            except Exception:
                status = "fallback"
                page["sections_source"] = "template_fallback"
                enrich_page_sections(page, hearing)
                section_count = len(page.get("sections") or [])
            finally:
                async with llm_lock:
                    finished_chars += int(page_chars.pop(slug, 0))
                    page_started.pop(slug, None)
                    active.discard(slug)
                    llm_done += 1
                phase = "llm_timeout" if status == "timeout" else "llm"
                await emit(slug, phase, section_count=section_count, force=True)

    ticker_task: asyncio.Task | None = None
    if llm_jobs and progress:
        ticker_task = asyncio.create_task(progress_ticker())
    try:
        if llm_jobs:
            await asyncio.gather(*[plan_one(page) for page, _group in llm_jobs])
        elif progress:
            await emit("", "llm", force=True)
    finally:
        stop_ticker.set()
        if ticker_task is not None:
            try:
                await ticker_task
            except Exception:
                pass

    refresh_blueprint_stats(blueprint)
    blueprint.setdefault("ai_stages", {})["planner"] = "complete"
    blueprint["ai_stages"]["planner_model"] = planner
    blueprint["ai_stages"]["planner_mode"] = "llm"
    blueprint["ai_stages"]["planner_llm_pages"] = total_llm
    blueprint["ai_stages"]["planner_template_pages"] = template_count
    blueprint["ai_stages"]["writer"] = "pending"
    blueprint["ai_stages"]["content_model"] = None
    return blueprint


def strip_blueprint_section_content(blueprint: dict[str, Any]) -> None:
    """Ensure AI-1 blueprint sections never carry content text (AI-2 only)."""
    for key in ("pages", "seo_pages", "tag_pages"):
        for page in blueprint.get(key) or []:
            if not isinstance(page, dict):
                continue
            cleaned: list[dict[str, Any]] = []
            for sec in page.get("sections") or []:
                if not isinstance(sec, dict):
                    continue
                row = {k: v for k, v in sec.items() if k not in FORBIDDEN_SECTION_KEYS}
                row.pop("text", None)
                cleaned.append(row)
            page["sections"] = cleaned
