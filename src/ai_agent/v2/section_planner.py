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
from ai_agent.v2.section_rules import enrich_page_sections

VALID_MODES = frozenset({"generate", "facts", "expand", "shell", "blank"})

PLANNER_SYSTEM = """You are BBS satellite WordPress section planner (AI-1).
Plan section BLOCK STRUCTURE for AI-2 to write copy later. You do NOT write website content.

Rules:
- Output a single JSON object only. No markdown, no explanation.
- Shape: {"sections": [{"id": "snake_case", "label": "short English label", "mode": "generate|facts|expand|shell|blank", "rule": "short Japanese instruction for AI-2"}]}
- NEVER output final page copy, paragraphs, headings, or customer-facing text.
- NEVER use keys: text, content, body, copy, html, paragraphs — only id, label, mode, rule.
- rule: brief instruction for AI-2 (max ~200 chars), not the final文案.
- section id: unique on this page, snake_case, 2–24 chars [a-z0-9_]
- mode blank: when page must stay empty (menu blank directive)
- mode shell: listing-only pages (blog/sitemap) — structure only
- mode facts: tell AI-2 to use exact hearing facts (names/prices/hours)
- Do not add pages — only sections for the given page
- 2–8 sections per page unless leave_blank (then 1 section mode blank is ok)
"""

FORBIDDEN_SECTION_KEYS = frozenset({"text", "content", "body", "copy", "html", "paragraphs", "body_paragraphs"})
MAX_RULE_LEN = 400
PLANNER_CONCURRENCY = 3
PLANNER_PAGE_TIMEOUT_SEC = 35.0
# Typical AI-1 JSON size for one page (used for smooth % while streaming).
PLANNER_EXPECTED_CHARS = 650
PLANNER_STREAM_EMIT_CHARS = 28
PLANNER_STREAM_EMIT_SEC = 0.2
SHELL_PAGE_TYPES = frozenset({"blog", "sitemap", "privacy", "column", "seo", "tag", "news"})
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
    )
    compact: dict[str, Any] = {}
    for key in keys:
        val = prod.get(key)
        if val:
            compact[key] = val
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
    return out


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
        ids = [str(s.get("id")) for s in template if isinstance(s, dict)]
        lines.append("template_hint_ids (may adapt): " + ", ".join(ids))
    return "\n".join(lines)


def _planner_messages(hearing: dict[str, Any], page: dict[str, Any]) -> list[ChatMessage]:
    compact = _compact_hearing_for_planner(hearing)
    user = (
        "Plan section blocks for this satellite WordPress page.\n\n"
        "=== PAGE ===\n"
        + _page_context_block(page, hearing)
        + "\n\n=== HEARING FACTS (compact) ===\n"
        + json.dumps(compact, ensure_ascii=False, indent=2)
        + '\n\nReturn JSON only (structure — NO page copy): {"sections": [{"id":"...","label":"...","mode":"...","rule":"short instruction for AI-2"}]}'
    )
    return [
        ChatMessage(role="system", content=PLANNER_SYSTEM),
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
) -> list[dict[str, str]]:
    messages = _planner_messages(hearing, page)
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
                        content='Fix JSON. Return only: {"sections": [{"id":"hero","label":"Hero","mode":"generate","rule":"..."}]}',
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
) -> dict[str, Any]:
    """Replace template sections with AI-1 planned sections (parallel LLM for nav content pages)."""
    llm_jobs: list[tuple[dict[str, Any], str]] = []
    template_count = 0

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
