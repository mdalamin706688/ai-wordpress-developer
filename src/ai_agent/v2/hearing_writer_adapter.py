"""Map v2 hearing JSON → v1 production hearing for AI writer / fact_pack."""

from __future__ import annotations

from typing import Any

from ai_agent.pipeline.hearing_adapter import prepare_hearing_for_production


def v2_hearing_to_production(hearing: dict[str, Any]) -> dict[str, Any]:
    project = hearing.get("project") or {}
    store = hearing.get("store") or {}
    wg = hearing.get("writing_guidance") or {}
    out: dict[str, Any] = {
        "business_name": str(project.get("business_name") or store.get("name") or "").strip(),
        "area": str(project.get("area") or "").strip(),
        "address": str(store.get("address") or "").strip(),
        "phone": str(store.get("phone") or "").strip(),
        "concept": str(hearing.get("concept_global") or "").strip(),
        "catchcopy": "",
        "reservation": str(wg.get("reservation_methods") or wg.get("reservation_flow") or "").strip(),
        "payment": str(store.get("other") or "").strip(),
        "parking": "",
        "first_visit": str(wg.get("reservation_flow") or "").strip(),
        "target": str(project.get("purpose") or "").strip(),
        "tone": str(project.get("writing_request") or wg.get("writing_tone") or "").strip(),
        "services": [],
        "menu": [],
        "forbidden": [],
        "missing": [],
        "focus_keywords": list(hearing.get("focus_keywords") or []),
        "tag_keywords": list(hearing.get("tag_keywords") or []),
        "reference_sites": [
            str(r.get("url") or "")
            for r in (hearing.get("reference_sites") or [])
            if isinstance(r, dict) and str(r.get("url") or "").strip()
        ],
        "writing_guidance": {
            k: str(v or "").strip()
            for k, v in wg.items()
            if str(v or "").strip()
        },
        "page_directives": dict(hearing.get("page_directives") or {}),
        "industry": str(project.get("industry") or "").strip(),
        "design_request": str(project.get("design_request") or "").strip(),
        "cv_destination": str(wg.get("cv_destination") or "").strip(),
        "selling_points": str(wg.get("selling_points") or "").strip(),
        "atmosphere": str(wg.get("atmosphere") or "").strip(),
        "ng_tone": str(wg.get("ng_tone") or "").strip(),
    }
    hours_open = str(store.get("hours_open") or "").strip()
    hours_close = str(store.get("hours_close") or "").strip()
    if hours_open or hours_close:
        out["hours"] = f"{hours_open}–{hours_close}".strip("–")
    out["closed"] = str(store.get("closed") or "").strip()

    # page composition ② conditionals + page facts for AI-2
    flags = hearing.get("flags") if isinstance(hearing.get("flags"), dict) else {}
    out["flags"] = {
        "include_reviews": bool(flags.get("include_reviews")),
        "include_recruit": bool(flags.get("include_recruit")),
        "include_ai_blog": bool(flags.get("include_ai_blog")),
    }
    out["production_kind"] = str(project.get("production_kind") or "").strip()
    out["site_purpose"] = str(project.get("purpose") or "").strip()
    out["public_domain"] = str(project.get("domain") or "").strip()
    out["site_category"] = str(
        project.get("site_category") or hearing.get("site_category") or ""
    ).strip()
    brief = project.get("site_brief") if isinstance(project.get("site_brief"), dict) else hearing.get("site_brief")
    if isinstance(brief, dict) and brief:
        out["site_brief"] = brief
    out["ai_support"] = str(project.get("ai_support") or "").strip()
    out["existing_url"] = str(project.get("existing_url") or "").strip()
    out["existing_site_copy"] = str(project.get("existing_site_copy") or "").strip()
    reviews = hearing.get("reviews") or []
    if isinstance(reviews, list) and reviews:
        out["reviews"] = reviews
    recruit = hearing.get("recruit") if isinstance(hearing.get("recruit"), dict) else {}
    if recruit:
        out["recruit"] = recruit
    ai_blog = hearing.get("ai_blog") if isinstance(hearing.get("ai_blog"), dict) else {}
    if ai_blog:
        out["ai_blog"] = ai_blog
    note = str(hearing.get("top_inherit_note") or "").strip()
    if note:
        out["top_inherit_note"] = note

    for page in hearing.get("pages") or []:
        if not isinstance(page, dict):
            continue
        ptype = str(page.get("type") or "")
        items = [str(x).strip() for x in (page.get("items") or []) if str(x).strip()]
        if ptype == "メニュー (総合)":
            out["menu"] = [{"name": line, "duration": "", "price": ""} for line in items]
        elif ptype == "サービス":
            out["services"] = items
        elif ptype == "コンセプト" and items and not out["concept"]:
            out["concept"] = "。".join(items[:3])
        elif ptype == "よくある質問" and items:
            out["faq_items"] = items

    focus = hearing.get("focus_keywords") or []
    if focus and "重点:" not in str(out.get("concept") or ""):
        out["concept"] = (out.get("concept") or "") + " 重点: " + "、".join(focus)

    return prepare_hearing_for_production(out)
