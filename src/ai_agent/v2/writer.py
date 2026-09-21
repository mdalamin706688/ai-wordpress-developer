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
from ai_agent.v2.fact_slots import enforce_hearing_fact_slots
from ai_agent.v2.hearing_writer_adapter import v2_hearing_to_production
from ai_agent.v2.prompt_packs import default_ai2_system_for_type
from ai_agent.v2.prompt_rules import format_v2_page_rules, json_example_for_page, prompt_page_key, section_ids_for_page


# Fallback only — lab should pass the per-type English AI-2 pack.
V2_WRITER_SYSTEM = default_ai2_system_for_type("type3")

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
) -> dict[str, Any]:
    data = _loads_sections_object(content)
    sections = data.get("sections") if isinstance(data, dict) else None
    if isinstance(sections, dict):
        return {str(k): _normalize_section_value(v) for k, v in sections.items()}
    if isinstance(data, dict) and expected_ids:
        matched = {
            sid: _normalize_section_value(data[sid])
            for sid in expected_ids
            if sid in data and data[sid] is not None
        }
        if matched:
            return matched
    # Legacy v1 copy shape → best-effort map for a single hero/body block page.
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        if data.get("heading"):
            out["hero"] = str(data.get("heading") or "")
        if data.get("lead"):
            out["hero"] = (str(out.get("hero") or "") + "\n" + str(data.get("lead") or "")).strip()
        body = data.get("body_paragraphs") or []
        if isinstance(body, list) and body:
            out["body"] = "\n\n".join(str(p) for p in body if str(p).strip())
        if data.get("cta"):
            out["cta"] = str(data.get("cta") or "")
        if out:
            return out
    preview = (content or "").strip().replace("\n", " ")[:240]
    raise ValueError(f"invalid AI output — missing sections object (preview: {preview})")


def _normalize_section_value(value: Any) -> Any:
    """Keep nested content-block objects; stringify leaves."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return {str(k): _normalize_section_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_section_value(v) for v in value]
    return str(value).strip()


def _coerce_nested_to_catalog_fields(section_id: str, value: Any) -> Any:
    """Align AI-2 nested keys to catalog fields (e.g. body → description)."""
    from ai_agent.v2.page_catalog import empty_nested_value, nested_fields_for_section

    fields = nested_fields_for_section({"id": section_id})
    if not fields:
        return _normalize_section_value(value)
    if not isinstance(value, dict):
        # empty / wrong type → empty nested object
        if not str(value or "").strip():
            return empty_nested_value(fields)
        return _normalize_section_value(value)
    raw = {str(k): _normalize_section_value(v) for k, v in value.items()}
    out: dict[str, Any] = {}
    for field in fields:
        if field in raw and str(raw.get(field) or "").strip():
            out[field] = raw[field]
        elif field == "description" and str(raw.get("body") or "").strip():
            out[field] = raw["body"]
        elif field == "body" and str(raw.get("description") or "").strip():
            out[field] = raw["description"]
        else:
            out[field] = raw.get(field, "")
    return out


def coerce_page_section_text(page: dict[str, Any], section_text: dict[str, Any]) -> dict[str, Any]:
    """Force nested objects onto catalog field names for every section id."""
    out: dict[str, Any] = {}
    known = [
        str(sec.get("id") or "")
        for sec in (page.get("sections") or [])
        if isinstance(sec, dict) and sec.get("id")
    ]
    known_set = set(known)
    for key, val in (section_text or {}).items():
        sid = str(key)
        if known_set and sid not in known_set:
            continue
        out[sid] = _coerce_nested_to_catalog_fields(sid, val)
    for sid in known:
        if sid not in out:
            out[sid] = _coerce_nested_to_catalog_fields(sid, "")
    return out


def _section_value_as_text(value: Any) -> str:
    """Serialize nested section values for Excel/CSV text cells."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if not any(str(v or "").strip() for v in value.values() if not isinstance(v, (dict, list))):
            # all leaf strings empty → treat as blank cell
            if not any(isinstance(v, (dict, list)) and v for v in value.values()):
                return ""
        return json.dumps(value, ensure_ascii=False, indent=4)
    if isinstance(value, list):
        if not value:
            return ""
        return json.dumps(value, ensure_ascii=False, indent=4)
    return str(value).strip()


def ground_sections(sections: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, text in sections.items():
        if isinstance(text, dict):
            out[key] = {
                k: _strip_unsupported(str(v or ""), hearing).strip() if not isinstance(v, (dict, list)) else v
                for k, v in text.items()
            }
        elif isinstance(text, list):
            out[key] = text
        else:
            out[key] = _strip_unsupported(str(text or ""), hearing).strip()
    return out


def enforce_blank_page_copy(
    sections: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any],
) -> dict[str, Any]:
    """Force empty strings when page is blank / reviews lack bodies / greeting lacks staff."""
    from ai_agent.v2.page_catalog import empty_nested_value, nested_fields_for_section
    from ai_agent.v2.section_rules import (
        hearing_has_staff_greeting_facts,
        hearing_review_bodies,
    )

    force = bool(page.get("leave_blank") or page.get("force_blank_copy"))
    slug = str(page.get("slug") or "")
    ptype = str(page.get("type") or "")
    if slug == "reviews" and not hearing_review_bodies(hearing):
        force = True
    if slug in {"greeting", "staff"} or "スタッフ" in ptype or "挨拶" in ptype:
        if not hearing_has_staff_greeting_facts(hearing):
            force = True

    def _blank_for_key(key: str, current: Any) -> Any:
        fields = nested_fields_for_section(key)
        if fields:
            return empty_nested_value(fields)
        if isinstance(current, dict):
            return {k: "" for k in current}
        return ""

    if force:
        return {key: _blank_for_key(key, val) for key, val in sections.items()}

    # FAQ: blank Q&A body aliases (faq_items / faq_list / items / …); keep hero/cta.
    from ai_agent.v2.section_rules import hearing_faq_items, is_faq_qa_section_id

    if page.get("faq_items_blank") or (
        (slug == "faq" or "質問" in ptype) and not hearing_faq_items(hearing)
    ):
        out = dict(sections)
        for key in list(out):
            if is_faq_qa_section_id(key):
                out[key] = _blank_for_key(key, out.get(key))
        return out
    return sections


def _build_page_messages(
    *,
    hearing_prod: dict[str, Any],
    hearing_v2: dict[str, Any],
    page: dict[str, Any],
    system_prompt: str,
    user_template: str,
    type24_extras: str | None = None,
) -> list[ChatMessage]:
    hearing_block = (
        "Permitted hearing facts (source of truth — do not invent beyond this):\n"
        + json.dumps(hearing_prod, ensure_ascii=False, indent=2)
    )
    rules = format_v2_page_rules(page, hearing_v2, type24_extras=type24_extras)
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
    section_text: dict[str, Any],
) -> None:
    for row in rows:
        if str(row.get("page_slug") or row.get("page_id")) != page_slug:
            continue
        sid = str(row.get("section_id") or "")
        if sid not in section_text:
            continue
        text = _section_value_as_text(section_text[sid])
        if text:
            row["text"] = text


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


def blank_section_text(page: dict[str, Any]) -> dict[str, Any]:
    from ai_agent.v2.page_catalog import empty_nested_value, nested_fields_for_section

    out: dict[str, Any] = {}
    for sec in page.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        sid = str(sec.get("id") or "")
        if not sid:
            continue
        fields = nested_fields_for_section(sec)
        out[sid] = empty_nested_value(fields) if fields else ""
    return out


def pages_to_write(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    """Pages that need AI-2 LLM content (excludes blank and pure shell-only)."""
    out: list[dict[str, Any]] = []
    for page in _iter_blueprint_pages(blueprint):
        if page.get("leave_blank") or page.get("force_blank_copy"):
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
        if page.get("leave_blank") or page.get("force_blank_copy"):
            continue
        modes = _section_modes(page)
        if modes and modes <= {"shell", "blank"}:
            out.append(page)
    return out


def shell_section_text(page: dict[str, Any], hearing: dict[str, Any] | None = None) -> dict[str, Any]:
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

    by_type: dict[str, dict[str, Any]] = {
        "sitemap": {
            "listing_intro": {
                "heading": f"{site}サイトマップ",
                "lead": (
                    f"{site}のサイトマップです。"
                    "各ページの構成をご確認のうえ、目的のページへお進みください。"
                ),
            },
            "hero": (
                f"{site}のサイトマップです。"
                "各ページの構成をご確認のうえ、目的のページへお進みください。"
            ),
        },
        "privacy": {
            "listing_intro": {
                "heading": "プライバシーポリシー",
                "lead": (
                    f"{site}（プライバシーポリシー）です。"
                    "お客様からお預かりする個人情報の取り扱いについて定めています。"
                ),
            },
            "hero": (
                f"{site}（プライバシーポリシー）です。"
                "お客様からお預かりする個人情報の取り扱いについて定めています。"
                "詳細のご確認・ご質問はお問い合わせページよりご連絡ください。"
            ),
        },
        "blog": {
            "listing_intro": {
                "heading": "ブログ",
                "lead": f"{site}のブログ一覧です。最新のお知らせ・施工事例・役立つ情報を順次公開します。",
            },
            "hero": (
                f"{site}のブログ一覧です。"
                "最新のお知らせ・施工事例・役立つ情報を順次公開します。"
            ),
            "cta": {
                "label": "お問い合わせ",
                "phone": "",
                "url": "",
                "line_url": "",
                "methods": "",
            },
        },
        "ai_blog": {
            "listing_intro": {
                "heading": "AIブログ",
                "lead": f"{site}のAIブログ一覧です。AIサポート付きの記事を順次公開します。",
            },
            "hero": (
                f"{site}のAIブログ一覧です。"
                "AIサポート付きの記事を順次公開します。"
            ),
            "cta": {
                "label": "お問い合わせ",
                "phone": "",
                "url": "",
                "line_url": "",
                "methods": "",
            },
        },
        "column": {
            "listing_intro": {
                "heading": "コラム",
                "lead": f"{site}のコラム一覧です。専門知識や現場のポイントを分かりやすくお伝えします。",
            },
            "hero": (
                f"{site}のコラム一覧です。"
                "専門知識や現場のポイントを分かりやすくお伝えします。"
            ),
            "cta": {
                "label": "お問い合わせ",
                "phone": "",
                "url": "",
                "line_url": "",
                "methods": "",
            },
        },
        "新着情報": {
            "listing_intro": {
                "heading": "新着情報",
                "lead": f"{site}の新着情報一覧です。最新のお知らせをこちらでご確認ください。",
            },
            "hero": f"{site}の新着情報一覧です。最新のお知らせをこちらでご確認ください。",
            "cta": {
                "label": "お問い合わせ",
                "phone": "",
                "url": "",
                "line_url": "",
                "methods": "",
            },
        },
    }
    preset = by_type.get(ptype) or {}
    out: dict[str, Any] = {}
    for sec in page.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        sid = str(sec.get("id") or "")
        if not sid:
            continue
        if sid in preset and preset[sid]:
            out[sid] = preset[sid]
        else:
            label = str(sec.get("label") or sid)
            fields = sec.get("fields")
            if isinstance(fields, list) and fields:
                out[sid] = {
                    str(f): (f"{site}の{nav}" if i == 0 else "")
                    for i, f in enumerate(fields)
                }
            else:
                out[sid] = f"{site}の{nav}（{label}）です。サイトの固定ページとしてご利用ください。"
    return out


def fill_empty_shell_sections(
    page: dict[str, Any],
    section_text: dict[str, Any],
    hearing: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        cur = out.get(sid)
        empty = False
        if cur is None or cur == "":
            empty = True
        elif isinstance(cur, dict) and not any(_s for _s in (_section_value_as_text(cur),) if _s):
            empty = True
        if empty:
            out[sid] = shell_fill.get(sid) or out.get(sid) or ""
    return out


def pages_leave_blank(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        p
        for p in _iter_blueprint_pages(blueprint)
        if p.get("leave_blank") or p.get("force_blank_copy")
    ]


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
    type24_extras: str | None = None,
):
    del quality, verifier_pool  # v2 section writer uses writer model only (v1 stack expects flat copy schema)
    from ai_agent.v2.site_category import attach_site_category

    hearing_v2 = attach_site_category(dict(hearing_v2 or {}))
    hearing_prod = v2_hearing_to_production(hearing_v2)
    hearing_prod["target_page"] = prompt_page_key(page)
    messages = _build_page_messages(
        hearing_prod=hearing_prod,
        hearing_v2=hearing_v2,
        page=page,
        system_prompt=system_prompt,
        user_template=user_template,
        type24_extras=type24_extras,
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
            # Facts first, then blank rules win (greeting/reviews/FAQ Q&A / leave_blank).
            sections = enforce_hearing_fact_slots(sections, page, hearing_v2)
            sections = enforce_blank_page_copy(sections, page, hearing_v2)
            sections = coerce_page_section_text(page, sections)
            from ai_agent.v2.category_guard import (
                apply_category_guards,
                repair_user_message,
            )

            sections, _applied, remaining = apply_category_guards(sections, page, hearing_v2)
            # One repair pass for leftover audience / soft issues the scrub couldn't fix.
            soft_ok = {
                i
                for i in remaining
                if i.startswith("wrong_audience:sales_copy_on_recruit_site")
            }
            hard = [i for i in remaining if i not in soft_ok]
            if hard and attempt < 2:
                messages = list(messages) + [
                    ChatMessage(role="assistant", content=last_raw[:4000]),
                    ChatMessage(role="user", content=repair_user_message(hard, page)),
                ]
                continue
            stack = SimpleNamespace(                copy={"sections": sections},
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
