"""Category playbooks + post-AI-2 guards for Type 3 (and siblings)."""

from __future__ import annotations

import json
import re
from typing import Any

from ai_agent.v2.site_category import derive_site_category

_RANKING_RE = re.compile(
    r"(地域\s*1\s*番店|地域一番|地域No\.?\s*1|No\.?\s*1|ナンバーワン|一番店|業界一|日本一)",
    re.I,
)
_RECRUIT_COPY_RE = re.compile(
    r"(求人応募|採用応募|エントリーはこちら|履歴書|面接日程|募集要項|中途採用|新卒採用|"
    r"ジョブオファー|求職者の皆様|一緒に働きませんか)",
)
_LEAD_COPY_RE = re.compile(
    r"(無料見積|お問い合わせはこちら|今すぐ相談|塗装工事のご相談|施工のご依頼)",
)


def _s(value: Any) -> str:
    return str(value or "").strip()


def category_playbook_lines(category: str) -> list[str]:
    """Short fixed rules per category — injected into prompts."""
    cat = _s(category) or "general"
    common = [
        "PLAYBOOK:",
        "- Use only hearing facts. Empty when missing.",
        "- Nested fields must match page_rules / catalog (description not body when required).",
        "- Never invent rankings/awards unless hearing states them.",
    ]
    by_cat: dict[str, list[str]] = {
        "lead_gen": [
            "- Category lead_gen (集客): write for customers seeking services.",
            "- Prioritize service clarity, trust, and inquiry CTA (phone/LINE/form from hearing).",
            "- CTA label: clear action (無料相談・お見積りなど) — never leave label empty when phone/LINE exist.",
            "- Catchphrase: ONE emotional 15–28字 line; put name-origin / longer story only in short_description.",
            "- Area: use the composed hearing area (半島・県 when both appear) across TOP and landings — not prefecture-only.",
            "- Expand EVERY section from 売り / page-add / focus seeds (title+description); no thin one-liners.",
            "- Do not write hiring / job-application copy.",
        ],
        "recruit": [
            "- Category is hiring (制作種別 / 求人 pages): write for job seekers.",
            "- Use hearing hiring fields only (keywords / message / 制作種別).",
            "- Do not invent openings, salary, benefits, or headcount.",
            "- Do not write customer sales CTAs as the main goal.",
        ],
        "branding": [
            "- Category branding: emphasize brand story from hearing seeds only.",
            "- Keep claims soft; no invented awards.",
        ],
        "info": [
            "- Category info: informative tone for readers; no hard-sell invention.",
        ],
        "service": [
            "- Category service: explain services from page-add seeds; CTA from hearing CV.",
        ],
        "general": [
            "- Category general: follow page-add types and hearing seeds only.",
        ],
    }
    return common + by_cat.get(cat, by_cat["general"])


def playbook_lines_for_hearing(hearing: dict[str, Any] | None) -> list[str]:
    brief = derive_site_category(hearing)
    return category_playbook_lines(brief.get("category") or "general")


def _hearing_blob(hearing: dict[str, Any]) -> str:
    try:
        return json.dumps(hearing, ensure_ascii=False)
    except Exception:
        return _s(hearing)


def _walk_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_walk_strings(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_walk_strings(v))
    elif value is not None:
        t = _s(value)
        if t:
            out.append(t)
    return out


def _map_strings(value: Any, fn) -> Any:
    if isinstance(value, dict):
        return {k: _map_strings(v, fn) for k, v in value.items()}
    if isinstance(value, list):
        return [_map_strings(v, fn) for v in value]
    if isinstance(value, str):
        return fn(value)
    if value is None:
        return ""
    return fn(str(value))


def _strip_ranking(text: str, *, allowed: bool) -> str:
    if allowed or not text:
        return text
    return _RANKING_RE.sub("", text).strip()


def validate_page_sections(
    sections: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any],
) -> list[str]:
    """Return issue codes remaining after (or before) scrub."""
    from ai_agent.v2.page_catalog import nested_fields_for_section

    issues: list[str] = []
    brief = derive_site_category(hearing)
    cat = brief.get("category") or "general"
    blob = _hearing_blob(hearing)
    ranking_ok = bool(_RANKING_RE.search(blob))

    for sid, val in (sections or {}).items():
        fields = nested_fields_for_section({"id": str(sid)})
        if fields and isinstance(val, dict):
            if "description" in fields and "body" in val and not _s(val.get("description")):
                issues.append(f"field_alias:{sid}:body->description")
            extra = set(val.keys()) - set(fields)
            # allow empty extras only if they have content wrongly
            for ek in extra:
                if _s(val.get(ek)) and ek in {"body", "text"} and "description" in fields:
                    issues.append(f"wrong_field:{sid}:{ek}")
        for piece in _walk_strings(val):
            if not ranking_ok and _RANKING_RE.search(piece):
                issues.append(f"invented_ranking:{sid}")
                break

    slug = _s(page.get("slug"))
    ptype = _s(page.get("type"))
    joined = "\n".join(_walk_strings(sections))
    if cat in {"lead_gen", "service", "branding", "general", "info"} and slug != "recruit" and "リクルート" not in ptype:
        if _RECRUIT_COPY_RE.search(joined):
            issues.append("wrong_audience:recruit_copy_on_non_recruit")
    if cat == "recruit" and slug in {"home", "concept", "service"}:
        # soft: heavy lead-gen sales lines without recruit context
        if _LEAD_COPY_RE.search(joined) and not any(
            x in joined for x in ("求人", "採用", "募集", "応募")
        ):
            issues.append("wrong_audience:sales_copy_on_recruit_site")

    # FAQ intro empty while generate — soft issue
    if (slug == "faq" or "質問" in ptype) and isinstance(sections.get("faq_intro"), dict):
        intro = sections.get("faq_intro") or {}
        if not any(_s(v) for v in intro.values()):
            mode = ""
            for sec in page.get("sections") or []:
                if isinstance(sec, dict) and sec.get("id") == "faq_intro":
                    mode = _s(sec.get("mode"))
            if mode in {"generate", "expand", ""}:
                issues.append("empty_faq_intro")

    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def scrub_page_sections(
    sections: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Deterministic fixes. Returns (sections, applied_fix_codes)."""
    from ai_agent.v2.page_catalog import empty_nested_value, nested_fields_for_section

    applied: list[str] = []
    brief = derive_site_category(hearing)
    cat = brief.get("category") or "general"
    blob = _hearing_blob(hearing)
    ranking_ok = bool(_RANKING_RE.search(blob))
    out = dict(sections or {})

    def coerce_one(sid: str, value: Any) -> Any:
        fields = nested_fields_for_section({"id": sid})
        if not fields:
            return value
        if not isinstance(value, dict):
            if not _s(value):
                return empty_nested_value(fields)
            return value
        raw = {str(k): v for k, v in value.items()}
        fixed: dict[str, Any] = {}
        changed = False
        for field in fields:
            if field in raw and _s(raw.get(field)):
                fixed[field] = raw[field]
            elif field == "description" and _s(raw.get("body")):
                fixed[field] = raw["body"]
                changed = True
            elif field == "body" and _s(raw.get("description")):
                fixed[field] = raw["description"]
                changed = True
            else:
                fixed[field] = raw.get(field, "")
        if changed:
            applied.append(f"coerced_fields:{sid}")
        return fixed

    coerced = {str(sid): coerce_one(str(sid), val) for sid, val in out.items()}
    out = coerced

    def strip_rank(s: str) -> str:
        ns = _strip_ranking(s, allowed=ranking_ok)
        if ns != s:
            applied.append("stripped_ranking")
        return ns

    out = _map_strings(out, strip_rank)

    slug = _s(page.get("slug"))
    ptype = _s(page.get("type"))
    if cat in {"lead_gen", "service", "branding", "general", "info"} and slug != "recruit" and "リクルート" not in ptype:

        def strip_recruit(s: str) -> str:
            ns = _RECRUIT_COPY_RE.sub("", s).strip()
            if ns != s:
                applied.append("stripped_recruit_copy")
            return ns

        out = _map_strings(out, strip_recruit)

    # Minimal FAQ intro shell when empty
    if (slug == "faq" or "質問" in ptype) and "faq_intro" in {
        str(sec.get("id") or "") for sec in (page.get("sections") or []) if isinstance(sec, dict)
    }:
        intro = out.get("faq_intro")
        if not isinstance(intro, dict) or not any(_s(v) for v in intro.values()):
            fields = nested_fields_for_section({"id": "faq_intro"}) or ["heading", "lead"]
            filled = {f: ("" if f != "heading" else "よくあるご質問") for f in fields}
            out["faq_intro"] = filled
            applied.append("filled_faq_intro_heading")

    seen: set[str] = set()
    applied_u = []
    for a in applied:
        if a not in seen:
            seen.add(a)
            applied_u.append(a)
    return out, applied_u


def repair_user_message(issues: list[str], page: dict[str, Any]) -> str:
    """One-shot repair instruction for AI-2."""
    from ai_agent.v2.prompt_rules import json_example_for_page

    lines = [
        "Fix the JSON for THIS page. Keep hearing facts only.",
        "Issues to fix:",
    ]
    for i in issues[:12]:
        lines.append(f"- {i}")
    lines.append(
        "Rules: correct nested field names; remove invented rankings; "
        "match SITE BRIEF audience; empty when no hearing fact."
    )
    lines.append("JSON only:")
    lines.append(json_example_for_page(page))
    return "\n".join(lines)


def apply_category_guards(
    sections: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Scrub then validate. Returns sections, applied, remaining_issues."""
    from ai_agent.v2.site_category import attach_site_category

    hearing = attach_site_category(dict(hearing or {}))
    cleaned, applied = scrub_page_sections(sections, page, hearing)
    remaining = validate_page_sections(cleaned, page, hearing)
    return cleaned, applied, remaining
