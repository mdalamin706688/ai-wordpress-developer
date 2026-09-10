"""AI-2: write section text for v2 satellite blueprint using lab model stack."""

from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace
from typing import Any

from ai_agent.models.registry import ModelRegistry
from ai_agent.models.types import ChatMessage
from ai_agent.pipeline.ai_stack import WRITER_TEMPERATURE, extra_body_for, writer_max_tokens_for
from ai_agent.pipeline.grounding import _strip_unsupported
from ai_agent.v2.hearing_writer_adapter import v2_hearing_to_production
from ai_agent.v2.prompt_rules import format_v2_page_rules, json_example_for_page, prompt_page_key, section_ids_for_page


V2_WRITER_SYSTEM = """You are a Japanese website copywriter for BBS satellite sites.
Use ONLY facts from the hearing. Output a single JSON object.
Keys: sections (object mapping section id → Japanese text string).
No markdown. No invented prices, addresses, or claims. Empty string if unknown."""

# Per-page wall clock. Gemini free-tier may sleep ~20–60s on RPM 429 inside the call.
WRITER_PAGE_TIMEOUT_SEC = 90.0
WRITER_PAGE_TIMEOUT_GEMINI_SEC = 180.0
WRITER_PAGE_TIMEOUT_GEMINI_HEAVY_SEC = 240.0  # 3.6+ / non-lite: room for 429 waits
CharDeltaCallback = Any  # async (chars: int) -> None


def _is_gemini(model_id: str) -> bool:
    mid = str(model_id or "").lower()
    return mid.startswith("gemini") or "gemini" in mid


def _is_gemini_flash_lite(model_id: str) -> bool:
    mid = str(model_id or "").lower()
    return "flash-lite" in mid or "flash_lite" in mid


def _is_gemini_heavy_flash(model_id: str) -> bool:
    """Non-lite Gemini Flash — tighter free RPM than Lite (kept for 3.5 Flash pacing)."""
    mid = str(model_id or "").lower()
    if not _is_gemini(mid) or _is_gemini_flash_lite(mid):
        return False
    return "flash" in mid


def page_timeout_sec(model_id: str) -> float:
    if _is_gemini_heavy_flash(model_id):
        return WRITER_PAGE_TIMEOUT_GEMINI_HEAVY_SEC
    if _is_gemini(model_id):
        return WRITER_PAGE_TIMEOUT_GEMINI_SEC
    return WRITER_PAGE_TIMEOUT_SEC


def gemini_inter_page_sleep_sec(model_id: str) -> float:
    """Seconds to wait between AI-2 pages so free-tier RPM (~15–20) is less likely."""
    mid = str(model_id or "").lower()
    if not _is_gemini(mid):
        return 0.0
    if _is_gemini_flash_lite(mid):
        return 2.5
    # gemini-3.5-flash (non-lite)
    return 4.5


def gemini_writer_token_cap(model_id: str, base: int) -> int:
    """Keep Flash outputs lean so pages finish before free RPM windows slam shut."""
    mid = str(model_id or "").lower()
    if _is_gemini_flash_lite(mid):
        return min(base, 2800)
    if mid.startswith("gemini-"):
        return min(base, 3000)
    return base


def _loads_sections_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("invalid AI output — expected JSON object with sections")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("invalid AI output — expected JSON object with sections")
    blob = text[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # Trailing commas / minor issues — try a conservative cleanup.
        cleaned = re.sub(r",\s*}", "}", blob)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        return json.loads(cleaned)


def parse_v2_sections_json(
    content: str,
    *,
    expected_ids: list[str] | None = None,
) -> dict[str, str]:
    data = _loads_sections_object(content)
    sections = data.get("sections") if isinstance(data, dict) else None
    if isinstance(sections, dict):
        return {str(k): str(v or "").strip() for k, v in sections.items()}
    if isinstance(data, dict) and expected_ids:
        matched = {
            sid: str(data[sid] or "").strip()
            for sid in expected_ids
            if sid in data and data[sid] is not None
        }
        if matched:
            return matched
    # Legacy v1 copy shape → best-effort map for a single hero/body block page.
    if isinstance(data, dict):
        out: dict[str, str] = {}
        if data.get("heading"):
            out["hero"] = str(data.get("heading") or "")
        if data.get("lead"):
            out["hero"] = (out.get("hero", "") + "\n" + str(data.get("lead") or "")).strip()
        body = data.get("body_paragraphs") or []
        if isinstance(body, list) and body:
            out["body"] = "\n\n".join(str(p) for p in body if str(p).strip())
        if data.get("cta"):
            out["cta"] = str(data.get("cta") or "")
        if out:
            return out
    preview = (content or "").strip().replace("\n", " ")[:240]
    raise ValueError(f"invalid AI output — missing sections object (preview: {preview})")


def ground_sections(sections: dict[str, str], hearing: dict[str, Any]) -> dict[str, str]:
    return {
        key: _strip_unsupported(str(text or ""), hearing).strip()
        for key, text in sections.items()
    }


def _build_page_messages(
    *,
    hearing_prod: dict[str, Any],
    hearing_v2: dict[str, Any],
    page: dict[str, Any],
    system_prompt: str,
    user_template: str,
) -> list[ChatMessage]:
    hearing_block = (
        "許可された事実:\n"
        + json.dumps(hearing_prod, ensure_ascii=False, indent=2)
    )
    rules = format_v2_page_rules(page, hearing_v2)
    user = (user_template or "").strip()
    if "{hearing}" in user:
        user = user.replace("{hearing}", hearing_block)
    else:
        user = (user + "\n\n" if user else "") + hearing_block
    if "{page_rules}" in user:
        user = user.replace("{page_rules}", rules)
    else:
        user = user.rstrip() + "\n\n" + rules
    ids = section_ids_for_page(page)
    if ids:
        user = user.rstrip() + "\n\n必須 section id: " + ", ".join(ids)
        user += "\nJSONのみ返答: " + json_example_for_page(page)
    system = (system_prompt or "").strip() or V2_WRITER_SYSTEM
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]


def apply_sections_to_rows(
    rows: list[dict[str, str]],
    *,
    page_slug: str,
    section_text: dict[str, str],
) -> None:
    for row in rows:
        if str(row.get("page_slug") or row.get("page_id")) != page_slug:
            continue
        sid = str(row.get("section_id") or "")
        if sid in section_text and section_text[sid]:
            row["text"] = section_text[sid]


def _section_modes(page: dict[str, Any]) -> set[str]:
    return {
        str(s.get("mode") or "")
        for s in (page.get("sections") or [])
        if isinstance(s, dict)
    }


def _iter_blueprint_pages(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("pages", "seo_pages", "tag_pages"):
        for page in blueprint.get(key) or []:
            if isinstance(page, dict):
                out.append(page)
    return out


def blank_section_text(page: dict[str, Any]) -> dict[str, str]:
    return {
        str(sec.get("id") or ""): ""
        for sec in (page.get("sections") or [])
        if isinstance(sec, dict) and str(sec.get("id") or "")
    }


def pages_to_write(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    """Pages that need AI-2 LLM content (excludes blank and pure shell-only)."""
    out: list[dict[str, Any]] = []
    for page in _iter_blueprint_pages(blueprint):
        if page.get("leave_blank"):
            continue
        modes = _section_modes(page)
        if modes <= {"shell", "blank"}:
            continue
        out.append(page)
    return out


def pages_shell_only(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    """Pages whose sections are only shell/blank (e.g. sitemap, privacy) — no LLM."""
    out: list[dict[str, Any]] = []
    for page in _iter_blueprint_pages(blueprint):
        if page.get("leave_blank"):
            continue
        modes = _section_modes(page)
        if modes and modes <= {"shell", "blank"}:
            out.append(page)
    return out


def shell_section_text(page: dict[str, Any], hearing: dict[str, Any] | None = None) -> dict[str, str]:
    """Deterministic Japanese copy for shell sections so export is not empty."""
    hearing = hearing or {}
    site = str(
        (hearing.get("project") or {}).get("name")
        or hearing.get("site_name")
        or page.get("title")
        or "当サイト"
    ).strip() or "当サイト"
    # Prefer short brand from page title 「…｜店名」
    title = str(page.get("title") or "")
    if "｜" in title:
        site = title.split("｜")[-1].strip() or site
    nav = str(page.get("nav_label") or page.get("slug") or "このページ")
    ptype = str(page.get("type") or page.get("slug") or "").lower()

    by_type: dict[str, dict[str, str]] = {
        "sitemap": {
            "hero": (
                f"{site}のサイトマップです。"
                "各ページの構成をご確認のうえ、目的のページへお進みください。"
            ),
        },
        "privacy": {
            "hero": (
                f"{site}（プライバシーポリシー）です。"
                "お客様からお預かりする個人情報の取り扱いについて定めています。"
                "詳細のご確認・ご質問はお問い合わせページよりご連絡ください。"
            ),
        },
        "blog": {
            "hero": (
                f"{site}のブログ一覧です。"
                "最新のお知らせ・施工事例・役立つ情報を順次公開します。"
            ),
            "cta": f"{site}へのご相談・お見積りはお問い合わせページよりご連絡ください。",
        },
        "column": {
            "hero": (
                f"{site}のコラム一覧です。"
                "専門知識や現場のポイントを分かりやすくお伝えします。"
            ),
            "cta": f"詳しくは{site}までお気軽にお問い合わせください。",
        },
        "新着情報": {
            "hero": f"{site}の新着情報一覧です。最新のお知らせをこちらでご確認ください。",
            "cta": f"ご予約・ご相談は{site}までお問い合わせください。",
        },
    }
    preset = by_type.get(ptype) or {}
    out: dict[str, str] = {}
    for sec in page.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        sid = str(sec.get("id") or "")
        if not sid:
            continue
        if sid in preset and preset[sid].strip():
            out[sid] = preset[sid].strip()
        else:
            label = str(sec.get("label") or sid)
            out[sid] = f"{site}の{nav}（{label}）です。サイトの固定ページとしてご利用ください。"
    return out


def fill_empty_shell_sections(
    page: dict[str, Any],
    section_text: dict[str, str],
    hearing: dict[str, Any] | None = None,
) -> dict[str, str]:
    """After AI-2, fill any still-empty shell-mode sections with deterministic copy."""
    out = dict(section_text or {})
    shell_ids = [
        str(sec.get("id") or "")
        for sec in (page.get("sections") or [])
        if isinstance(sec, dict) and str(sec.get("mode") or "") == "shell" and sec.get("id")
    ]
    if not shell_ids:
        return out
    shell_fill = shell_section_text(page, hearing)
    for sid in shell_ids:
        if not str(out.get(sid) or "").strip():
            out[sid] = shell_fill.get(sid) or out.get(sid) or ""
    return out


def pages_leave_blank(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in _iter_blueprint_pages(blueprint) if p.get("leave_blank")]


async def write_page(
    *,
    registry: ModelRegistry,
    hearing_v2: dict[str, Any],
    page: dict[str, Any],
    writer: str,
    quality: str,
    verifier_pool: list[str],
    system_prompt: str,
    user_template: str,
    mode: str = "production",
    on_chars: CharDeltaCallback | None = None,
):
    del quality, verifier_pool  # v2 section writer uses writer model only (v1 stack expects flat copy schema)
    hearing_prod = v2_hearing_to_production(hearing_v2)
    hearing_prod["target_page"] = prompt_page_key(page)
    messages = _build_page_messages(
        hearing_prod=hearing_prod,
        hearing_v2=hearing_v2,
        page=page,
        system_prompt=system_prompt,
        user_template=user_template,
    )
    expected_ids = section_ids_for_page(page)
    max_tokens = gemini_writer_token_cap(writer, writer_max_tokens_for(writer))
    mid = str(writer or "").lower()
    # Match v1: Gemini minimal thinking / GLM thinking disabled + JSON mode when needed.
    chat_kwargs: dict[str, Any] = {}
    extra = dict(extra_body_for(writer) or {})
    if mid.startswith("gemini") or "gemini" in mid:
        extra["response_format"] = {"type": "json_object"}
    if extra:
        chat_kwargs["extra_body"] = extra

    use_stream = mid.startswith("gemini") or "gemini" in mid or mid.startswith("nvidia")
    last_raw = ""
    last_error: Exception | None = None
    json_mode = bool(chat_kwargs.get("extra_body"))
    timeout_sec = page_timeout_sec(writer)
    # Heavy Flash: allow two timeout retries (429 waits eat the wall clock).
    timeout_retries_left = 2 if _is_gemini_heavy_flash(writer) else (1 if timeout_sec >= 120 else 0)

    async def _one_call() -> str:
        temp = WRITER_TEMPERATURE if mode != "raw" else 0.7
        if use_stream:
            parts: list[str] = []
            async for token in registry.chat_stream(
                writer,
                messages,
                temperature=temp,
                max_tokens=max_tokens,
                **chat_kwargs,
            ):
                if not token:
                    continue
                parts.append(token)
                if on_chars is not None:
                    await on_chars(sum(len(p) for p in parts))
            return "".join(parts).strip()
        result = await asyncio.to_thread(
            registry.chat,
            writer,
            messages,
            temperature=temp,
            max_tokens=max_tokens,
            **chat_kwargs,
        )
        text = (result.content or "").strip()
        if on_chars is not None and text:
            await on_chars(len(text))
        return text

    def _is_rate_limit(exc: BaseException) -> bool:
        text = str(exc).lower()
        return (
            "http 429" in text
            or "resource_exhausted" in text
            or "rate limit" in text
            or "exceeded your current quota" in text
            or "too many requests" in text
        )

    for attempt in range(4 if _is_gemini_heavy_flash(writer) else 3):
        try:
            last_raw = await asyncio.wait_for(_one_call(), timeout=timeout_sec)
        except asyncio.TimeoutError as exc:
            if timeout_retries_left > 0:
                timeout_retries_left -= 1
                await asyncio.sleep(3.0)
                continue
            slug = str(page.get("slug") or page.get("id") or "page")
            raise TimeoutError(
                f"{slug}: AI-2 timed out after {int(timeout_sec)}s "
                f"({writer}). Retry the page or switch model."
            ) from exc
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < 3:
                from ai_agent.models.providers import retry_sleep_seconds

                wait = retry_sleep_seconds(429, str(exc), attempt)
                await asyncio.sleep(wait)
                continue
            if json_mode and attempt == 0:
                # Drop response_format only; keep thinking controls if present.
                body = dict(chat_kwargs.get("extra_body") or {})
                if "response_format" in body:
                    body.pop("response_format", None)
                    if body:
                        chat_kwargs["extra_body"] = body
                    else:
                        chat_kwargs.pop("extra_body", None)
                    json_mode = False
                    continue
                chat_kwargs.pop("extra_body", None)
                json_mode = False
                continue
            raise
        if not last_raw:
            last_error = RuntimeError(f"{writer} returned empty content")
            if attempt < 2:
                if _is_gemini(writer):
                    await asyncio.sleep(2.0 + attempt)
                messages = list(messages) + [
                    ChatMessage(
                        role="user",
                        content="空でした。JSONのみ返答してください: " + json_example_for_page(page),
                    ),
                ]
                continue
            raise last_error
        try:
            sections = parse_v2_sections_json(last_raw, expected_ids=expected_ids)
            sections = ground_sections(sections, hearing_prod)
            stack = SimpleNamespace(
                copy={"sections": sections},
                models_used=[writer],
                stream_writer=writer,
            )
            return stack, sections
        except ValueError as exc:
            last_error = exc
            if attempt < 2:
                messages = list(messages) + [
                    ChatMessage(role="assistant", content=last_raw[:4000]),
                    ChatMessage(
                        role="user",
                        content=(
                            "JSON形式が不正です。説明文なしで次の形のみ返してください:\n"
                            + json_example_for_page(page)
                        ),
                    ),
                ]
                continue
            slug = str(page.get("slug") or page.get("id") or "page")
            raise ValueError(f"{slug}: {exc}") from exc

    if last_error:
        raise last_error
    raise RuntimeError(f"{writer} failed to produce sections JSON")
