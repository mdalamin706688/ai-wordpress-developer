"""Derive Type 3 satellite site category from THIS hearing (purpose + kind + pages)."""

from __future__ import annotations

from typing import Any


def _s(value: Any) -> str:
    return str(value or "").strip()


def derive_site_category(hearing: dict[str, Any] | None) -> dict[str, str]:
    """Return a compact site brief used by AI-1 / AI-2 for Type 3 (and siblings).

    Categories (hearing-driven, not a fixed industry list):
    - recruit: 制作種別=リクルート / recruit page seeds
    - lead_gen: サイト制作目的 contains 集客
    - branding: purpose contains ブランディング
    - info: purpose contains 情報 / メディア
    - service: service/concept page-adds without a stronger purpose signal
    - general: fallback satellite
    """
    hearing = hearing if isinstance(hearing, dict) else {}
    project = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    flags = hearing.get("flags") if isinstance(hearing.get("flags"), dict) else {}
    recruit = hearing.get("recruit") if isinstance(hearing.get("recruit"), dict) else {}

    purpose = _s(project.get("purpose"))
    kind = _s(project.get("production_kind")) or _s(recruit.get("production_kind"))
    domain = _s(project.get("domain"))
    industry = _s(project.get("industry")) or _s(project.get("industry_category"))
    area = _s(project.get("area"))
    name = _s(project.get("business_name"))

    page_types = [
        _s(p.get("type"))
        for p in (hearing.get("pages") or [])
        if isinstance(p, dict) and _s(p.get("type"))
    ]
    has_recruit_page = any("リクルート" in t or "求人" in t for t in page_types)
    has_service = any("サービス" in t for t in page_types)
    has_concept = any("コンセプト" in t for t in page_types)

    is_recruit = bool(flags.get("include_recruit")) or "リクルート" in kind or "求人" in kind or has_recruit_page

    if is_recruit:
        category = "recruit"
        audience = "job_seekers"
        goal = "hiring_applications"
    elif "集客" in purpose:
        category = "lead_gen"
        audience = "customers"
        goal = "service_inquiries"
    elif "ブランディング" in purpose:
        category = "branding"
        audience = "customers"
        goal = "brand_awareness"
    elif "情報" in purpose or "メディア" in purpose:
        category = "info"
        audience = "readers"
        goal = "information"
    elif has_service or has_concept:
        category = "service"
        audience = "customers"
        goal = "service_inquiries"
    else:
        category = "general"
        audience = "visitors"
        goal = "site_goals_from_hearing"

    return {
        "category": category,
        "purpose": purpose,
        "production_kind": kind,
        "domain": domain,
        "industry": industry,
        "area": area,
        "business_name": name,
        "audience": audience,
        "goal": goal,
    }


def site_brief_lines(hearing: dict[str, Any] | None) -> list[str]:
    """English prompt lines — category comes from THIS hearing only."""
    from ai_agent.v2.category_guard import category_playbook_lines

    brief = derive_site_category(hearing)
    cat = brief.get("category") or "general"
    lines = [
        "SITE BRIEF (from THIS hearing — decide tone and copy for this category):",
        f"- category: {cat}",
    ]
    if brief.get("purpose"):
        lines.append(f"- サイト制作目的: {brief['purpose']}")
    if brief.get("production_kind"):
        lines.append(f"- 制作種別: {brief['production_kind']}")
    if brief.get("domain"):
        lines.append(f"- 公開ドメイン: {brief['domain']}")
    if brief.get("industry"):
        lines.append(f"- industry: {brief['industry']}")
    if brief.get("area"):
        lines.append(f"- area: {brief['area']}")
    lines.append(f"- audience: {brief.get('audience')}")
    lines.append(f"- goal: {brief.get('goal')}")
    lines.extend(category_playbook_lines(cat))
    return lines


def attach_site_category(hearing: dict[str, Any]) -> dict[str, Any]:
    """Mutate hearing with project.site_category + site_brief."""
    brief = derive_site_category(hearing)
    project = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    project = dict(project)
    project["site_category"] = brief.get("category") or "general"
    project["site_brief"] = brief
    hearing["project"] = project
    hearing["site_category"] = brief.get("category") or "general"
    hearing["site_brief"] = brief
    return hearing
