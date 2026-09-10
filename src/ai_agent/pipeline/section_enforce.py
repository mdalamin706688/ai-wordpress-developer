"""Enforce predefined TOP/Service section checklist against generated copy."""

from __future__ import annotations

from typing import Any

from ai_agent.pipeline.facts import copy_blob
from ai_agent.pipeline.prompt_rules import section_items_for
from ai_agent.pipeline.section_pages import build_section_bundle


def _s(value: Any) -> str:
    return str(value or "").strip()


def required_section_ids(page: str, hearing: dict[str, Any]) -> list[str]:
    """Sections that must be present for this page (skip optional missing ones)."""
    key = (page or "top").strip().lower()
    missing = " ".join(str(x) for x in (hearing.get("missing") or []))
    if key in {"service", "services"}:
        return ["hero", "services", "reservation"]
    if key == "concept":
        return ["hero", "points", "cta"]
    if key == "greeting":
        has_staff = any(_s(hearing.get(k)) for k in ("staff", "staff_name", "therapist", "greeting"))
        return ["hero", "message", "cta"] if has_staff and "スタッフ紹介" not in missing else []
    if key == "menu":
        return ["hero", "items", "cta"]
    if key == "faq":
        return ["hero", "items", "cta"]
    if key == "feature":
        return ["hero", "points", "cta"]
    if key == "access":
        return ["hero", "details", "cta"]
    if key == "reviews":
        has_reviews = bool(hearing.get("reviews"))
        return ["hero", "items", "cta"] if has_reviews and "お客様の声" not in missing else []
    if key in {"blog", "column"}:
        return []  # shell pages — no AI coverage check

    required = ["hero", "about", "concept", "menu", "access", "reservation"]
    has_staff = any(_s(hearing.get(k)) for k in ("staff", "staff_name", "therapist", "greeting"))
    has_reviews = bool(hearing.get("reviews"))
    if has_staff and "スタッフ紹介" not in missing:
        required.append("greeting")
    if has_reviews and "お客様の声" not in missing:
        required.append("reviews")
    return required


def _section_covered(section_id: str, page: str, blob: str, hearing: dict[str, Any]) -> bool:
    key = (page or "top").strip().lower()
    if key in {"service", "services"}:
        if section_id == "hero":
            return bool(_s(hearing.get("concept")) and _s(hearing.get("concept")) in blob) or len(blob) > 40
        if section_id == "services":
            menu = hearing.get("menu") or []
            names = [_s(i.get("name")) for i in menu if isinstance(i, dict) and _s(i.get("name"))]
            if not names:
                return True
            return all(name in blob for name in names)
        if section_id == "reservation":
            phone = _s(hearing.get("phone"))
            return (phone and phone in blob) or "予約" in blob or "ご予約" in blob
        return True

    if key in {"concept", "feature"} and section_id in {"hero", "points"}:
        concept = _s(hearing.get("concept"))
        return (concept and concept[:20] in blob) or len(blob) > 40
    if key == "menu" and section_id == "items":
        menu = hearing.get("menu") or []
        names = [_s(i.get("name")) for i in menu if isinstance(i, dict) and _s(i.get("name"))]
        return all(n in blob for n in names) if names else True
    if key == "access" and section_id == "details":
        station = _s(hearing.get("station"))
        address = _s(hearing.get("address"))
        return (station and station.split()[0] in blob) or (address and address[:8] in blob)
    if key == "faq" and section_id == "items":
        return len(blob) > 40 or bool(_s(hearing.get("hours")) or _s(hearing.get("phone")))
    if section_id in {"cta", "notes", "map", "message"}:
        return True

    if section_id == "hero":
        catch = _s(hearing.get("catchcopy"))
        name = _s(hearing.get("business_name"))
        return (catch and catch in blob) or (name and name in blob) or len(blob) > 40
    if section_id in {"about", "concept", "points"}:
        concept = _s(hearing.get("concept"))
        return (concept and concept[:20] in blob) or len(blob) > 80
    if section_id == "menu":
        menu = hearing.get("menu") or []
        prices = [_s(i.get("price")) for i in menu if isinstance(i, dict) and _s(i.get("price"))]
        names = [_s(i.get("name")) for i in menu if isinstance(i, dict) and _s(i.get("name"))]
        if prices:
            return any(p in blob for p in prices)
        return any(n in blob for n in names) if names else True
    if section_id == "access":
        station = _s(hearing.get("station"))
        address = _s(hearing.get("address"))
        return (station and station.split()[0] in blob) or (address and address[:8] in blob)
    if section_id == "reservation":
        phone = _s(hearing.get("phone"))
        return (phone and phone in blob) or "予約" in blob or "ご予約" in blob
    if section_id == "greeting":
        return any(_s(hearing.get(k)) in blob for k in ("staff", "staff_name", "greeting") if _s(hearing.get(k)))
    if section_id == "reviews":
        return "声" in blob or "クチコミ" in blob or "口コミ" in blob
    return True


def section_coverage_issues(
    copy: dict[str, Any],
    hearing: dict[str, Any],
    *,
    page: str = "top",
) -> list[dict[str, str]]:
    """Fail closed when a required checklist section is missing from the draft."""
    blob = copy_blob(copy)
    issues: list[dict[str, str]] = []
    labels = {i["id"]: i.get("label") or i["id"] for i in section_items_for(page)}
    for sid in required_section_ids(page, hearing):
        if _section_covered(sid, page, blob, hearing):
            continue
        issues.append(
            {
                "field": f"section.{sid}",
                "type": "SECTION_GAP",
                "generated": "",
                "suggestion": f"Required section missing: {labels.get(sid, sid)}",
            }
        )
    return issues


def attach_section_qa(
    copy: dict[str, Any],
    hearing: dict[str, Any],
    *,
    page: str = "top",
) -> dict[str, Any]:
    """Annotate copy with section bundle + coverage warnings (non-mutating facts)."""
    out = dict(copy)
    page_key = (page or out.get("slug") or "top")
    if str(page_key).lower() in {"home", "top", ""}:
        page_key = "top"
    bundle = build_section_bundle(hearing, out, page=str(page_key))
    gaps = section_coverage_issues(out, hearing, page=str(page_key))
    out["_sections"] = bundle
    out["_section_gaps"] = gaps
    warnings = list(out.get("_qa_warnings") or [])
    for gap in gaps:
        warnings.append(gap.get("suggestion") or "section gap")
    out["_qa_warnings"] = warnings
    return out
