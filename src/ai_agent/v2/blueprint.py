"""AI-1: page list from hearing; section blocks filled by AI-1 LLM (section_planner)."""

from __future__ import annotations

from typing import Any

from ai_agent.v2.page_catalog import sections_for_page_type
from ai_agent.v2.production_types import ProductionType
from ai_agent.v2.section_rules import enrich_page_sections
from ai_agent.v2.hearing_directives import (
    apply_directives_to_pages,
    attach_writing_push_seeds,
    company_page_request,
)

TYPE2_BLUEPRINT_VERSION = 1
TYPE3_BLUEPRINT_VERSION = 3
TYPE4_BLUEPRINT_VERSION = 1
TYPE3_MIN_NAV_PAGES = 12
TYPE3_STANDARD_NAV_SLUGS = (
    "home",
    "concept",
    "service",
    "faq",
    "greeting",
    "menu",
    "access",
    "blog",
    "reviews",
    "contact",
    "sitemap",
    "privacy",
    "column",
)

# Active production types in the v2 lab (/ai/v2/).
V2_LAB_ACTIVE_TYPES = frozenset(
    {
        ProductionType.TYPE2_RENEWAL.value,
        ProductionType.TYPE3_SATELLITE.value,
        ProductionType.TYPE4_SATELLITE_RENEWAL.value,
    }
)

_SATELLITE_NAV_TYPES = frozenset(
    {
        ProductionType.TYPE3_SATELLITE.value,
        ProductionType.TYPE4_SATELLITE_RENEWAL.value,
    }
)


def uses_satellite_nav(hearing: dict[str, Any] | None) -> bool:
    """Type 3 + Type 4 share satellite nav shells / inject."""
    return str((hearing or {}).get("production_type") or "") in _SATELLITE_NAV_TYPES


def refresh_blueprint_stats(blueprint: dict[str, Any]) -> None:
    """Recompute stats from page/section arrays (keeps UI + export in sync)."""
    from ai_agent.v2.writer import pages_leave_blank, pages_shell_only, pages_to_write

    pages = [p for p in (blueprint.get("pages") or []) if isinstance(p, dict)]
    seo = [p for p in (blueprint.get("seo_pages") or []) if isinstance(p, dict)]
    tags = [p for p in (blueprint.get("tag_pages") or []) if isinstance(p, dict)]
    stats = dict(blueprint.get("stats") or {})
    stats["nav_pages"] = len(pages)
    stats["content_pages"] = len(pages)
    stats["seo_pages"] = len(seo)
    stats["tag_pages"] = len(tags)
    stats["all_pages"] = len(pages) + len(seo) + len(tags)
    stats["total_sections"] = sum(len(p.get("sections") or []) for p in pages + seo + tags)
    stats["write_pages"] = len(pages_to_write(blueprint))
    stats["shell_pages"] = len(pages_shell_only(blueprint))
    stats["blank_pages"] = len(pages_leave_blank(blueprint))
    # Pages that receive section text in the AI-2 step (LLM + shell fill)
    stats["content_fill_pages"] = stats["write_pages"] + stats["shell_pages"]
    omitted = blueprint.get("omitted_pages") or []
    stats["omitted_pages"] = len(omitted) if isinstance(omitted, list) else 0
    blueprint["stats"] = stats


def omit_blank_pages_from_blueprint(blueprint: dict[str, Any]) -> list[dict[str, str]]:
    """Drop leave_blank pages entirely — do not keep empty site pages for export/AI-2.

    Hearing may flag 料金表/menu as blank when 項目内容 is empty; those pages are
    omitted from nav instead of shipping empty WordPress rows.
    """
    omitted: list[dict[str, str]] = list(blueprint.get("omitted_pages") or [])
    seen = {str(row.get("slug") or "") for row in omitted if isinstance(row, dict)}

    def _filter(key: str) -> None:
        kept: list[dict[str, Any]] = []
        for page in blueprint.get(key) or []:
            if not isinstance(page, dict):
                continue
            if not page.get("leave_blank"):
                kept.append(page)
                continue
            slug = str(page.get("slug") or page.get("id") or "")
            if slug and slug not in seen:
                omitted.append(
                    {
                        "slug": slug,
                        "label": str(page.get("nav_label") or slug),
                        "reason": str(
                            page.get("leave_blank_reason")
                            or "ヒアリングに掲載内容なし — ページ自体をサイト構成から除外"
                        ),
                    }
                )
                seen.add(slug)
        blueprint[key] = kept

    _filter("pages")
    _filter("seo_pages")
    _filter("tag_pages")
    blueprint["omitted_pages"] = omitted
    # Keep nav chips in sync with remaining pages.
    pages = [p for p in (blueprint.get("pages") or []) if isinstance(p, dict)]
    blueprint["nav"] = [
        {"id": p.get("id") or p.get("slug"), "label": p.get("nav_label"), "slug": p.get("slug")}
        for p in pages
    ]
    refresh_blueprint_stats(blueprint)
    return omitted


def inject_missing_type3_nav_pages(blueprint: dict[str, Any], hearing: dict[str, Any]) -> bool:
    """Add standard satellite nav shells when an older builder returned a short page list.

    Used for Type 3 (サテライト) and Type 4 (サテライトリニューアル).
    """
    if not uses_satellite_nav(hearing):
        return False
    pages = [p for p in (blueprint.get("pages") or []) if isinstance(p, dict)]
    seen = {str(p.get("slug") or "") for p in pages}
    name = _site_name(hearing)
    default_clone = (
        "bbs_satellite_renewal"
        if str(hearing.get("production_type") or "") == ProductionType.TYPE4_SATELLITE_RENEWAL.value
        else "bbs_satellite_template"
    )
    clone = str(blueprint.get("clone_mode") or default_clone)
    before = len(pages)
    _append_access_page(hearing, pages, seen, name=name, clone=clone)
    _append_blog_page(hearing, pages, seen, name=name, clone=clone)
    _append_reviews_page(hearing, pages, seen, name=name, clone=clone)
    _append_contact_page(hearing, pages, seen, name=name, clone=clone)
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen,
        page_id="sitemap",
        slug="sitemap",
        nav_label="サイトマップ",
        page_type="sitemap",
        name=name,
        clone=clone,
    )
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen,
        page_id="privacy",
        slug="privacy",
        nav_label="プライバシーポリシー",
        page_type="privacy",
        name=name,
        clone=clone,
    )
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen,
        page_id="column",
        slug="column",
        nav_label="コラム",
        page_type="column",
        name=name,
        clone=clone,
    )
    if len(pages) <= before:
        return False
    ref_order = list(TYPE3_STANDARD_NAV_SLUGS)
    by_slug = {str(p.get("slug") or ""): p for p in pages if p.get("slug")}
    ordered: list[dict[str, Any]] = []
    for slug in ref_order:
        if slug in by_slug:
            ordered.append(by_slug.pop(slug))
    for slug, page in by_slug.items():
        if slug:
            ordered.append(page)
    for page in ordered[before:]:
        enrich_page_sections(page, hearing)
    blueprint["pages"] = ordered
    blueprint["nav"] = [{"id": p["id"], "label": p["nav_label"], "slug": p["slug"]} for p in ordered]
    if not (blueprint.get("seo_pages") or []):
        blueprint["seo_pages"] = _build_seo_blueprints(hearing, name=name)
        for page in blueprint["seo_pages"]:
            enrich_page_sections(page, hearing)
    if not (blueprint.get("tag_pages") or []):
        blueprint["tag_pages"] = _build_tag_blueprints(hearing, name=name)
        for page in blueprint["tag_pages"]:
            enrich_page_sections(page, hearing)
    ptype = str(hearing.get("production_type") or "")
    blueprint["blueprint_version"] = (
        TYPE4_BLUEPRINT_VERSION
        if ptype == ProductionType.TYPE4_SATELLITE_RENEWAL.value
        else TYPE3_BLUEPRINT_VERSION
    )
    omit_blank_pages_from_blueprint(blueprint)
    refresh_blueprint_stats(blueprint)
    return True


def merge_type3_blueprint_pages(partial: dict[str, Any], shell: dict[str, Any]) -> dict[str, Any]:
    """Fill missing nav/SEO/tag pages from a fresh shell while keeping AI-1 section plans."""
    merged: dict[str, Any] = dict(shell)
    for key in (
        "satellite",
        "renewal",
        "clone_mode",
        "site_name",
        "production_type",
        "production_label",
    ):
        if partial.get(key) is not None:
            merged[key] = partial[key]
    stages = dict(shell.get("ai_stages") or {})
    stages.update(partial.get("ai_stages") or {})
    merged["ai_stages"] = stages

    def merge_page_lists(shell_pages: list[Any], partial_pages: list[Any]) -> list[dict[str, Any]]:
        partial_by_slug = {
            str(p.get("slug") or ""): p for p in partial_pages if isinstance(p, dict) and p.get("slug")
        }
        out_pages: list[dict[str, Any]] = []
        for sp in shell_pages:
            if not isinstance(sp, dict):
                continue
            slug = str(sp.get("slug") or "")
            pp = partial_by_slug.get(slug)
            if pp and pp.get("sections"):
                row = dict(sp)
                row.update(pp)
                row["sections"] = pp.get("sections") or sp.get("sections") or []
                if pp.get("sections_source"):
                    row["sections_source"] = pp["sections_source"]
                out_pages.append(row)
            else:
                out_pages.append(dict(sp))
        return out_pages

    merged["pages"] = merge_page_lists(list(shell.get("pages") or []), list(partial.get("pages") or []))
    merged["seo_pages"] = merge_page_lists(list(shell.get("seo_pages") or []), list(partial.get("seo_pages") or []))
    merged["tag_pages"] = merge_page_lists(list(shell.get("tag_pages") or []), list(partial.get("tag_pages") or []))
    merged["nav"] = [{"id": p["id"], "label": p["nav_label"], "slug": p["slug"]} for p in merged["pages"]]
    ptype = str(merged.get("production_type") or "")
    merged["blueprint_version"] = (
        TYPE4_BLUEPRINT_VERSION
        if ptype == ProductionType.TYPE4_SATELLITE_RENEWAL.value
        else TYPE3_BLUEPRINT_VERSION
    )
    refresh_blueprint_stats(merged)
    return merged


def finalize_type3_blueprint(partial: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Ensure full type3 nav + stats; keep AI-1 section plans from partial."""
    from ai_agent.v2.section_planner import strip_blueprint_section_content

    shell = build_site_blueprint(hearing)
    inject_missing_type3_nav_pages(shell, hearing)
    merged = merge_type3_blueprint_pages(partial, shell)
    strip_blueprint_section_content(merged)
    # Carry omitted list from shell (blank pages already dropped there).
    if shell.get("omitted_pages") and not merged.get("omitted_pages"):
        merged["omitted_pages"] = list(shell.get("omitted_pages") or [])
    omit_blank_pages_from_blueprint(merged)
    merged["blueprint_version"] = TYPE3_BLUEPRINT_VERSION
    return merged


def finalize_type4_blueprint(partial: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Ensure full type4 satellite-renewal nav + stats; keep AI-1 section plans."""
    from ai_agent.v2.section_planner import strip_blueprint_section_content

    shell = build_site_blueprint(hearing)
    inject_missing_type3_nav_pages(shell, hearing)
    merged = merge_type3_blueprint_pages(partial, shell)
    strip_blueprint_section_content(merged)
    if shell.get("omitted_pages") and not merged.get("omitted_pages"):
        merged["omitted_pages"] = list(shell.get("omitted_pages") or [])
    omit_blank_pages_from_blueprint(merged)
    merged["blueprint_version"] = TYPE4_BLUEPRINT_VERSION
    merged["production_type"] = ProductionType.TYPE4_SATELLITE_RENEWAL.value
    return merged


def type3_nav_probe_count() -> int:
    """How many nav pages the running server builds for the sample hearing."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    sample = root / "demo" / "v2" / "samples" / "type3-satellite.csv"
    if not sample.is_file():
        sample = root / "demo" / "v2" / "samples" / "type3-sateraito.csv"
    if not sample.is_file():
        return 0
    hearing = __import__("ai_agent.v2.hearing_parser", fromlist=["parse_hearing_sheet"]).parse_hearing_sheet(
        sample.read_text(encoding="utf-8-sig")
    )
    bp = build_type3_blueprint(hearing)
    inject_missing_type3_nav_pages(bp, hearing)
    return len(bp.get("pages") or [])


def _slug_for_type(page_type: str, explicit: str) -> str:
    if explicit:
        return explicit
    mapping = {
        "コンセプト": "concept",
        "サービス": "service",
        "メニュー (総合)": "menu",
        "よくある質問": "faq",
        "お客様の声": "reviews",
        "スタッフ (代表挨拶・代表のみ)": "greeting",
        "スタッフ (複数スタッフ・詳細有り)": "staff",
        "リクルート (総合)": "recruit",
        "問い合わせ (ご予約)": "contact",
        "ギャラリー (施工事例：詳細ページ有)": "gallery",
        "新着情報": "news",
    }
    return mapping.get(page_type, "page")


def _site_name(hearing: dict[str, Any]) -> str:
    project = hearing.get("project") or {}
    store = hearing.get("store") or {}
    return str(project.get("business_name") or store.get("name") or "Untitled")


def _append_hearing_pages(
    hearing: dict[str, Any],
    pages: list[dict[str, Any]],
    seen_slugs: set[str],
    *,
    name: str,
    clone: str,
) -> None:
    for slot in hearing.get("pages") or []:
        if not isinstance(slot, dict):
            continue
        ptype = str(slot.get("type") or "").strip()
        if not ptype:
            continue
        slug = str(slot.get("slug") or _slug_for_type(ptype, "")).strip() or _slug_for_type(ptype, "")
        if slug in seen_slugs:
            slug = f"{slug}-{slot.get('slot')}"
        seen_slugs.add(slug)
        label = str(slot.get("label") or ptype)
        pages.append(
            {
                "id": slug,
                "role": "content",
                "type": ptype,
                "slug": slug,
                "nav_label": label,
                "title": f"{label}｜{name}",
                "clone": clone,
                "sections": sections_for_page_type(ptype),
                "source": {
                    "kind": "hearing_page_slot",
                    "slot": slot.get("slot"),
                    "fields": [f"ページの追加{slot.get('slot')} (項目内容1..15)"],
                },
                "content_seeds": list(slot.get("items") or []),
            }
        )


def _append_access_page(
    hearing: dict[str, Any],
    pages: list[dict[str, Any]],
    seen_slugs: set[str],
    *,
    name: str,
    clone: str,
) -> None:
    flags = hearing.get("flags") or {}
    store = hearing.get("store") or {}
    if not (flags.get("access_page") or store.get("address")):
        return
    if "access" in seen_slugs:
        return
    pages.append(
        {
            "id": "access",
            "role": "utility",
            "type": "access",
            "slug": "access",
            "nav_label": "アクセス",
            "title": f"アクセス｜{name}",
            "clone": clone,
            "sections": sections_for_page_type("access"),
            "source": {"kind": "store", "fields": ["単独店舗 (住所)", "単独店舗 (電話番号)"]},
            "content_seeds": [],
        }
    )
    seen_slugs.add("access")


def _append_blog_page(
    hearing: dict[str, Any],
    pages: list[dict[str, Any]],
    seen_slugs: set[str],
    *,
    name: str,
    clone: str,
) -> None:
    if "blog" in seen_slugs:
        return
    pages.append(
        {
            "id": "blog",
            "role": "shell",
            "type": "blog",
            "slug": "blog",
            "nav_label": "ブログ",
            "title": f"ブログ｜{name}",
            "clone": clone,
            "sections": sections_for_page_type("blog"),
            "source": {"kind": "satellite_template", "fields": ["ブログはありますか"]},
            "content_seeds": [],
            "note": "Listing shell only — no individual posts generated.",
        }
    )
    seen_slugs.add("blog")


def _append_reviews_page(
    hearing: dict[str, Any],
    pages: list[dict[str, Any]],
    seen_slugs: set[str],
    *,
    name: str,
    clone: str,
) -> None:
    if "reviews" in seen_slugs:
        return
    pages.append(
        {
            "id": "reviews",
            "role": "utility",
            "type": "お客様の声",
            "slug": "reviews",
            "nav_label": "お客様の声",
            "title": f"お客様の声｜{name}",
            "clone": clone,
            "sections": sections_for_page_type("reviews"),
            "source": {"kind": "satellite_template", "fields": ["口コミ表示1..10"]},
            "content_seeds": [],
        }
    )
    seen_slugs.add("reviews")


def _append_contact_page(
    hearing: dict[str, Any],
    pages: list[dict[str, Any]],
    seen_slugs: set[str],
    *,
    name: str,
    clone: str,
) -> None:
    if "contact" in seen_slugs:
        return
    wg = hearing.get("writing_guidance") or {}
    seeds: list[str] = []
    cv = str(wg.get("cv_destination") or "").strip()
    if cv:
        seeds.append(cv)
    store = hearing.get("store") or {}
    phone = str(store.get("phone") or "").strip()
    if phone:
        seeds.append(f"電話: {phone}")
    pages.append(
        {
            "id": "contact",
            "role": "utility",
            "type": "contact",
            "slug": "contact",
            "nav_label": "お問い合わせ",
            "title": f"お問い合わせ｜{name}",
            "clone": clone,
            "sections": sections_for_page_type("contact"),
            "source": {"kind": "satellite_template", "fields": ["フォームはありますか", "CV先", "予約方法"]},
            "content_seeds": seeds,
        }
    )
    seen_slugs.add("contact")


def _append_utility_shell_page(
    *,
    pages: list[dict[str, Any]],
    seen_slugs: set[str],
    page_id: str,
    slug: str,
    nav_label: str,
    page_type: str,
    name: str,
    clone: str,
) -> None:
    if slug in seen_slugs:
        return
    pages.append(
        {
            "id": page_id,
            "role": "utility",
            "type": page_type,
            "slug": slug,
            "nav_label": nav_label,
            "title": f"{nav_label}｜{name}",
            "clone": clone,
            "sections": sections_for_page_type(page_type),
            "source": {"kind": "satellite_template", "fields": []},
            "content_seeds": [],
        }
    )
    seen_slugs.add(slug)


def _build_seo_blueprints(hearing: dict[str, Any], *, name: str) -> list[dict[str, Any]]:
    seo_blueprints: list[dict[str, Any]] = []
    for seo in hearing.get("seo_pages") or []:
        if not isinstance(seo, dict):
            continue
        n = seo.get("n")
        seo_blueprints.append(
            {
                "id": f"seo_{n}",
                "role": "seo",
                "type": "seo",
                "slug": f"seo-{n}",
                "nav_label": f"SEOページ{n}",
                "title": f"SEOページ{n}｜{name}",
                "clone": "bbs_seo_template",
                "sections": sections_for_page_type("seo"),
                "source": {"kind": "seo_page", "n": n},
                "content_seeds": list(hearing.get("focus_keywords") or []),
                "seo_overview": str(seo.get("overview") or "").strip(),
                "seo_sections": seo.get("sections") or {},
            }
        )
    return seo_blueprints


def _build_tag_blueprints(hearing: dict[str, Any], *, name: str) -> list[dict[str, Any]]:
    """One landing page per タグワードN — keyword-first, not a copy of SEO pages."""
    tag_blueprints: list[dict[str, Any]] = []
    tag_keywords = hearing.get("tag_keywords") or []
    for tag in hearing.get("tag_pages") or []:
        if not isinstance(tag, dict):
            continue
        n = tag.get("n")
        if not isinstance(n, int):
            continue
        kw = tag_keywords[n - 1] if 0 < n <= len(tag_keywords) else ""
        label = kw or f"タグページ{n}"
        tag_blueprints.append(
            {
                "id": f"tag_{n}",
                "role": "tag",
                "type": "tag",
                "slug": f"tag-{n}",
                "nav_label": label,
                "title": f"{label}｜{name}",
                "clone": "bbs_tag_template",
                "sections": sections_for_page_type("tag"),
                "source": {
                    "kind": "tag_page",
                    "n": n,
                    "fields": [f"タグワード{n}", f"タグページ{n} (指示)", f"タグページ{n} (内容)"],
                },
                "content_seeds": [kw] if kw else [],
                "tag_keyword": kw,
                "tag_instruction": tag.get("指示") or "",
                "tag_body": tag.get("内容") or "",
            }
        )
    return tag_blueprints


def _build_dynamic_refs(hearing: dict[str, Any]) -> list[dict[str, Any]]:
    dynamic_refs: list[dict[str, Any]] = []
    for dyn in hearing.get("dynamic_pages") or []:
        if not isinstance(dyn, dict):
            continue
        required = str(dyn.get("required") or "").strip()
        if required == "除外":
            dynamic_refs.append({**dyn, "ai_generate": False, "note": "Keep existing URL; do not generate posts."})
        else:
            dynamic_refs.append({**dyn, "ai_generate": False, "note": "Reference only."})
    return dynamic_refs


def _main_site_urls(hearing: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for ref in hearing.get("reference_sites") or []:
        if not isinstance(ref, dict):
            continue
        kind = str(ref.get("kind") or "")
        url = str(ref.get("url") or "").strip()
        if url and "お客様所有" in kind:
            urls.append(url)
    return urls


def _finish_blueprint(
    hearing: dict[str, Any],
    *,
    production_type: ProductionType,
    production_label: str,
    clone_mode: str,
    pages: list[dict[str, Any]],
    seo_blueprints: list[dict[str, Any]],
    tag_blueprints: list[dict[str, Any]],
    dynamic_refs: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = _site_name(hearing)
    bp: dict[str, Any] = {
        "version": 2,
        "blueprint_version": TYPE3_BLUEPRINT_VERSION,
        "production_type": production_type.value,
        "production_label": production_label,
        "clone_mode": clone_mode,
        "site_name": name,
        "pages": pages,
        "seo_pages": seo_blueprints,
        "tag_pages": tag_blueprints,
        "dynamic_references": dynamic_refs,
        "nav": [{"id": p["id"], "label": p["nav_label"], "slug": p["slug"]} for p in pages],
        "stats": {},
        "ai_stages": {
            "planner": "complete",
            "writer": "pending",
        },
    }
    if extra:
        bp.update(extra)
    refresh_blueprint_stats(bp)
    return bp


def build_type3_blueprint(hearing: dict[str, Any]) -> dict[str, Any]:
    """Type 3 サテライト — compact branch/landing site linked to client's main site."""
    name = _site_name(hearing)
    project = hearing.get("project") or {}
    clone = "bbs_satellite_template"
    pages: list[dict[str, Any]] = []
    seen_slugs: set[str] = {"home"}
    focus_keywords = list(hearing.get("focus_keywords") or [])
    main_sites = _main_site_urls(hearing)

    pages.append(
        {
            "id": "home",
            "role": "top",
            "type": "top_satellite",
            "slug": "home",
            "nav_label": "TOP",
            "title": f"{name}｜トップ",
            "clone": clone,
            "sections": sections_for_page_type("top_satellite"),
            "source": {
                "kind": "satellite_template",
                "fields": ["concept_global", "重点ワード1..5", "参考サイト (お客様所有)"],
            },
            "content_seeds": focus_keywords,
            "main_site_urls": main_sites,
        }
    )

    _append_hearing_pages(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_access_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_blog_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_reviews_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_contact_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen_slugs,
        page_id="sitemap",
        slug="sitemap",
        nav_label="サイトマップ",
        page_type="sitemap",
        name=name,
        clone=clone,
    )
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen_slugs,
        page_id="privacy",
        slug="privacy",
        nav_label="プライバシーポリシー",
        page_type="privacy",
        name=name,
        clone=clone,
    )
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen_slugs,
        page_id="column",
        slug="column",
        nav_label="コラム",
        page_type="column",
        name=name,
        clone=clone,
    )

    apply_directives_to_pages(pages, dict(hearing.get("page_directives") or {}))

    seo_blueprints = _build_seo_blueprints(hearing, name=name)
    tag_blueprints = _build_tag_blueprints(hearing, name=name)
    dynamic_refs = _build_dynamic_refs(hearing)

    for page in pages:
        enrich_page_sections(page, hearing)
    for page in seo_blueprints:
        enrich_page_sections(page, hearing)
    for page in tag_blueprints:
        enrich_page_sections(page, hearing)

    # Remove blank-flagged pages before finishing (no empty 料金表 in site map).
    omitted_preview: list[dict[str, str]] = []
    kept_pages: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, dict) and page.get("leave_blank"):
            omitted_preview.append(
                {
                    "slug": str(page.get("slug") or page.get("id") or ""),
                    "label": str(page.get("nav_label") or page.get("slug") or ""),
                    "reason": str(
                        page.get("leave_blank_reason")
                        or "ヒアリングに掲載内容なし — ページ自体をサイト構成から除外"
                    ),
                }
            )
        elif isinstance(page, dict):
            kept_pages.append(page)
    pages = kept_pages

    bp = _finish_blueprint(
        hearing,
        production_type=ProductionType.TYPE3_SATELLITE,
        production_label=hearing.get("production_label") or "サテライト",
        clone_mode="bbs_satellite_template",
        pages=pages,
        seo_blueprints=seo_blueprints,
        tag_blueprints=tag_blueprints,
        dynamic_refs=dynamic_refs,
        extra={
            "satellite": {
                "domain": str(project.get("domain") or ""),
                "purpose": str(project.get("purpose") or ""),
                "main_site_urls": main_sites,
                "reference_sites": list(hearing.get("reference_sites") or []),
                "focus_keywords": focus_keywords,
                "tag_keywords": list(hearing.get("tag_keywords") or []),
            },
            "omitted_pages": omitted_preview,
        },
    )
    omit_blank_pages_from_blueprint(bp)
    return bp


def build_type4_blueprint(hearing: dict[str, Any]) -> dict[str, Any]:
    """Type 4 サテライトリニューアル — satellite template + Type 2 renewal policies."""
    name = _site_name(hearing)
    project = hearing.get("project") or {}
    clone = "bbs_satellite_renewal"
    pages: list[dict[str, Any]] = []
    seen_slugs: set[str] = {"home"}
    focus_keywords = list(hearing.get("focus_keywords") or [])
    main_sites = _main_site_urls(hearing)
    existing_url = str(project.get("existing_url") or "").strip()

    pages.append(
        {
            "id": "home",
            "role": "top",
            "type": "top_satellite",
            "slug": "home",
            "nav_label": "TOP",
            "title": f"{name}｜トップ",
            "clone": clone,
            "sections": sections_for_page_type("top_satellite"),
            "source": {
                "kind": "satellite_renewal_top",
                "fields": ["既存URL", "TOP踏襲", "重点ワード1..5", "参考サイト (お客様所有)"],
            },
            "content_seeds": focus_keywords,
            "main_site_urls": main_sites,
            "existing_url": existing_url,
            "top_inherit": str(hearing.get("top_inherit_note") or ""),
        }
    )

    # Prefer ページの追加 (satellite); also honor 既存ページURL* when present.
    _append_hearing_pages(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_existing_pages(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_access_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_blog_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_reviews_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_contact_page(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen_slugs,
        page_id="sitemap",
        slug="sitemap",
        nav_label="サイトマップ",
        page_type="sitemap",
        name=name,
        clone=clone,
    )
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen_slugs,
        page_id="privacy",
        slug="privacy",
        nav_label="プライバシーポリシー",
        page_type="privacy",
        name=name,
        clone=clone,
    )
    _append_utility_shell_page(
        pages=pages,
        seen_slugs=seen_slugs,
        page_id="column",
        slug="column",
        nav_label="コラム",
        page_type="column",
        name=name,
        clone=clone,
    )

    apply_directives_to_pages(pages, dict(hearing.get("page_directives") or {}))
    attach_writing_push_seeds(pages, hearing)

    seo_blueprints = _build_seo_blueprints(hearing, name=name)
    tag_blueprints = _build_tag_blueprints(hearing, name=name)
    dynamic_refs = _build_dynamic_refs(hearing)

    for page in pages:
        enrich_page_sections(page, hearing)
    for page in seo_blueprints:
        enrich_page_sections(page, hearing)
    for page in tag_blueprints:
        enrich_page_sections(page, hearing)

    omitted_preview: list[dict[str, str]] = []
    kept_pages: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, dict) and page.get("leave_blank"):
            omitted_preview.append(
                {
                    "slug": str(page.get("slug") or page.get("id") or ""),
                    "label": str(page.get("nav_label") or page.get("slug") or ""),
                    "reason": str(
                        page.get("leave_blank_reason")
                        or "ヒアリングに掲載内容なし — ページ自体をサイト構成から除外"
                    ),
                }
            )
        elif isinstance(page, dict):
            kept_pages.append(page)
    pages = kept_pages

    excluded_existing = [
        {
            "n": s.get("n"),
            "page_name": s.get("page_name"),
            "url": s.get("url"),
            "required": s.get("required"),
        }
        for s in (hearing.get("existing_pages") or [])
        if isinstance(s, dict) and _is_excluded(str(s.get("required") or ""))
    ]

    bp = _finish_blueprint(
        hearing,
        production_type=ProductionType.TYPE4_SATELLITE_RENEWAL,
        production_label=hearing.get("production_label") or "サテライトリニューアル",
        clone_mode=clone,
        pages=pages,
        seo_blueprints=seo_blueprints,
        tag_blueprints=tag_blueprints,
        dynamic_refs=dynamic_refs,
        extra={
            "blueprint_version": TYPE4_BLUEPRINT_VERSION,
            "satellite": {
                "domain": str(project.get("domain") or ""),
                "purpose": str(project.get("purpose") or ""),
                "main_site_urls": main_sites,
                "reference_sites": list(hearing.get("reference_sites") or []),
                "focus_keywords": focus_keywords,
                "tag_keywords": list(hearing.get("tag_keywords") or []),
            },
            "renewal": {
                "existing_url": existing_url,
                "existing_site_colors": str(project.get("existing_site_colors") or ""),
                "existing_site_copy": str(project.get("existing_site_copy") or ""),
                "top_inherit": str(hearing.get("top_inherit_note") or ""),
                "page_count_declared": str(project.get("page_count_declared") or ""),
                "excluded_existing_pages": excluded_existing,
                "focus_keywords": focus_keywords,
                "tag_keywords": list(hearing.get("tag_keywords") or []),
            },
            "omitted_pages": omitted_preview,
        },
    )
    omit_blank_pages_from_blueprint(bp)
    return bp


def _nav_label_from_existing(page_name: str, fallback: str) -> str:
    label = str(page_name or "").strip()
    if " | " in label:
        label = label.split(" | ", 1)[0].strip()
    return label or fallback


def _slug_from_existing_url(url: str, *, n: int) -> str:
    from urllib.parse import urlparse

    path = (urlparse(str(url or "")).path or "").strip("/")
    if not path:
        return f"existing-{n}"
    segment = path.split("/")[-1].strip() or path.replace("/", "-")
    slug = _slugify_segment(segment)
    return slug or f"existing-{n}"


def _slugify_segment(text: str) -> str:
    t = str(text or "").strip().lower()
    if not t:
        return ""
    import re

    out = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return out


def _infer_existing_page_type(page_name: str, url: str) -> str:
    blob = f"{page_name} {url}".lower()
    if any(k in blob for k in ("works", "gallery", "施工", "事例")):
        return "ギャラリー (施工事例：詳細ページ有)"
    if any(k in blob for k in ("contact", "問い合わせ", "見積", "estimate")):
        return "問い合わせ (ご予約)"
    if any(k in blob for k in ("concept", "初めて", "about")):
        return "コンセプト"
    if any(k in blob for k in ("faq", "よくある質問")):
        return "よくある質問"
    if any(k in blob for k in ("menu", "メニュー", "料金")):
        return "メニュー (総合)"
    if any(k in blob for k in ("service", "サービス", "工事")):
        return "サービス"
    return "サービス"


def _is_excluded(required: str) -> bool:
    return str(required or "").strip() == "除外"


def _append_existing_pages(
    hearing: dict[str, Any],
    pages: list[dict[str, Any]],
    seen_slugs: set[str],
    *,
    name: str,
    clone: str,
) -> None:
    for slot in hearing.get("existing_pages") or []:
        if not isinstance(slot, dict):
            continue
        if _is_excluded(str(slot.get("required") or "")):
            continue
        url = str(slot.get("url") or "").strip()
        page_name = str(slot.get("page_name") or "").strip()
        if not url and not page_name:
            continue
        n = int(slot.get("n") or 0) or len(pages)
        slug = _slug_from_existing_url(url, n=n)
        if slug in seen_slugs:
            slug = f"{slug}-{n}"
        seen_slugs.add(slug)
        ptype = _infer_existing_page_type(page_name, url)
        label = _nav_label_from_existing(page_name, slug)
        pages.append(
            {
                "id": slug,
                "role": "content",
                "type": ptype,
                "slug": slug,
                "nav_label": label,
                "title": f"{label}｜{name}",
                "clone": clone,
                "sections": sections_for_page_type(ptype),
                "source": {
                    "kind": "existing_page",
                    "n": slot.get("n"),
                    "fields": [f"既存ページURL{slot.get('n')}"],
                    "url": url,
                },
                "content_seeds": [page_name, url] if page_name or url else [],
                "existing_url": url,
            }
        )


def finalize_type2_blueprint(partial: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Keep AI-1 plans; omit blanks; refresh stats (no satellite nav inject)."""
    from ai_agent.v2.section_planner import strip_blueprint_section_content

    merged = dict(partial or {})
    # Re-shell missing SEO/tag if planner returned a truncated list.
    shell = build_type2_blueprint(hearing)
    if not (merged.get("seo_pages") or []):
        merged["seo_pages"] = list(shell.get("seo_pages") or [])
    if not (merged.get("tag_pages") or []):
        merged["tag_pages"] = list(shell.get("tag_pages") or [])
    if not (merged.get("pages") or []):
        merged["pages"] = list(shell.get("pages") or [])
    # Prefer shell nav order when partial is short but keep AI-1 sections.
    if len(merged.get("pages") or []) < len(shell.get("pages") or []):
        merged = merge_type3_blueprint_pages(merged, shell)
    strip_blueprint_section_content(merged)
    if shell.get("omitted_pages") and not merged.get("omitted_pages"):
        merged["omitted_pages"] = list(shell.get("omitted_pages") or [])
    omit_blank_pages_from_blueprint(merged)
    merged["blueprint_version"] = TYPE2_BLUEPRINT_VERSION
    merged["production_type"] = ProductionType.TYPE2_RENEWAL.value
    refresh_blueprint_stats(merged)
    return merged


def build_type2_blueprint(hearing: dict[str, Any]) -> dict[str, Any]:
    """Type 2 リニューアル — renew existing client site from hearing (既存URL + 既存ページ)."""
    name = _site_name(hearing)
    project = hearing.get("project") or {}
    clone = "existing_client_site"
    pages: list[dict[str, Any]] = []
    seen_slugs: set[str] = {"home"}
    focus_keywords = list(hearing.get("focus_keywords") or [])
    existing_url = str(project.get("existing_url") or "").strip()

    pages.append(
        {
            "id": "home",
            "role": "top",
            "type": "top",
            "slug": "home",
            "nav_label": "TOP",
            "title": f"{name}｜トップ",
            "clone": clone,
            "sections": sections_for_page_type("top"),
            "source": {
                "kind": "renewal_top",
                "fields": ["既存URL", "TOP踏襲", "重点ワード1..5"],
            },
            "content_seeds": focus_keywords,
            "existing_url": existing_url,
            "top_inherit": str(hearing.get("top_inherit_note") or ""),
        }
    )

    _append_existing_pages(hearing, pages, seen_slugs, name=name, clone=clone)
    _append_hearing_pages(hearing, pages, seen_slugs, name=name, clone=clone)

    flags = hearing.get("flags") or {}

    # Contact from form slots marked 必要 (or present without 除外).
    # estimates is a separate inquiry page — do not treat it as a substitute for お問い合わせ.
    form_slots = [
        s
        for s in (hearing.get("form_pages") or [])
        if isinstance(s, dict) and not _is_excluded(str(s.get("required") or ""))
    ]
    if form_slots and "contact" not in seen_slugs:
        slot = form_slots[0]
        label = _nav_label_from_existing(str(slot.get("page_name") or ""), "お問い合わせ")
        pages.append(
            {
                "id": "contact",
                "role": "utility",
                "type": "contact",
                "slug": "contact",
                "nav_label": label,
                "title": f"{label}｜{name}",
                "clone": clone,
                "sections": sections_for_page_type("contact"),
                "source": {"kind": "existing_form", "fields": ["フォームURL1"], "url": slot.get("url")},
                "content_seeds": [str(slot.get("url") or "")],
                "existing_url": str(slot.get("url") or ""),
            }
        )
        seen_slugs.add("contact")
    elif flags.get("form") and "contact" not in seen_slugs and "estimates" not in seen_slugs:
        _append_contact_page(hearing, pages, seen_slugs, name=name, clone=clone)

    if flags.get("blog"):
        _append_blog_page(hearing, pages, seen_slugs, name=name, clone=clone)

    # Access only when hearing asks for it (or access URL slots exist) — not merely because address is filled.
    access_slots = [
        s
        for s in (hearing.get("access_pages") or [])
        if isinstance(s, dict)
        and not _is_excluded(str(s.get("required") or ""))
        and (str(s.get("url") or "").strip() or str(s.get("page_name") or "").strip())
    ]
    if flags.get("access_page") or access_slots:
        _append_access_page(hearing, pages, seen_slugs, name=name, clone=clone)

    # 備考 may rename アクセス → 会社概要 (/company) even when アクセスページはありますか=いいえ.
    company = (hearing.get("page_directives") or {}).get("_company_page") or company_page_request(
        str((hearing.get("writing_guidance") or {}).get("remarks") or "")
    )
    if isinstance(company, dict) and "company" not in seen_slugs and "access" not in seen_slugs:
        store = hearing.get("store") or {}
        label = str(company.get("nav_label") or "会社概要")
        seeds = list(company.get("extra_seeds") or [])
        for fact in (
            store.get("name"),
            store.get("address"),
            store.get("phone"),
            store.get("hours_open"),
            store.get("hours_close"),
            store.get("closed"),
        ):
            fact_s = str(fact or "").strip()
            if fact_s and fact_s not in seeds:
                seeds.append(fact_s)
        pages.append(
            {
                "id": "company",
                "role": "utility",
                "type": "access",
                "slug": "company",
                "nav_label": label,
                "title": f"{label}｜{name}",
                "clone": clone,
                "sections": sections_for_page_type("access"),
                "source": {
                    "kind": "remarks_company",
                    "fields": ["備考", "単独店舗 (住所)", "単独店舗 (電話番号)"],
                },
                "content_seeds": seeds,
                "note": str(company.get("reason") or ""),
            }
        )
        seen_slugs.add("company")

    sitemap = hearing.get("sitemap") or {}
    if (flags.get("sitemap") or sitemap.get("url")) and "sitemap" not in seen_slugs:
        _append_utility_shell_page(
            pages=pages,
            seen_slugs=seen_slugs,
            page_id="sitemap",
            slug="sitemap",
            nav_label=_nav_label_from_existing(str(sitemap.get("page_name") or ""), "サイトマップ"),
            page_type="sitemap",
            name=name,
            clone=clone,
        )

    privacy = hearing.get("privacy") or {}
    if (privacy.get("has_policy") or privacy.get("url")) and "privacy" not in seen_slugs:
        _append_utility_shell_page(
            pages=pages,
            seen_slugs=seen_slugs,
            page_id="privacy",
            slug="privacy",
            nav_label=_nav_label_from_existing(str(privacy.get("page_name") or ""), "プライバシーポリシー"),
            page_type="privacy",
            name=name,
            clone=clone,
        )

    apply_directives_to_pages(pages, dict(hearing.get("page_directives") or {}))
    attach_writing_push_seeds(pages, hearing)

    seo_blueprints = _build_seo_blueprints(hearing, name=name)
    tag_blueprints = _build_tag_blueprints(hearing, name=name)
    dynamic_refs = _build_dynamic_refs(hearing)

    for page in pages:
        enrich_page_sections(page, hearing)
    for page in seo_blueprints:
        enrich_page_sections(page, hearing)
    for page in tag_blueprints:
        enrich_page_sections(page, hearing)

    omitted_preview: list[dict[str, str]] = []
    kept_pages: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, dict) and page.get("leave_blank"):
            omitted_preview.append(
                {
                    "slug": str(page.get("slug") or page.get("id") or ""),
                    "label": str(page.get("nav_label") or page.get("slug") or ""),
                    "reason": str(
                        page.get("leave_blank_reason")
                        or "ヒアリングに掲載内容なし — ページ自体をサイト構成から除外"
                    ),
                }
            )
        elif isinstance(page, dict):
            kept_pages.append(page)
    pages = kept_pages

    # Existing pages marked 除外 stay out of nav but are noted for ops.
    excluded_existing = [
        {
            "n": s.get("n"),
            "page_name": s.get("page_name"),
            "url": s.get("url"),
            "required": s.get("required"),
        }
        for s in (hearing.get("existing_pages") or [])
        if isinstance(s, dict) and _is_excluded(str(s.get("required") or ""))
    ]

    bp = _finish_blueprint(
        hearing,
        production_type=ProductionType.TYPE2_RENEWAL,
        production_label=hearing.get("production_label") or "リニューアル",
        clone_mode=clone,
        pages=pages,
        seo_blueprints=seo_blueprints,
        tag_blueprints=tag_blueprints,
        dynamic_refs=dynamic_refs,
        extra={
            "blueprint_version": TYPE2_BLUEPRINT_VERSION,
            "renewal": {
                "existing_url": existing_url,
                "existing_site_colors": str(project.get("existing_site_colors") or ""),
                "existing_site_copy": str(project.get("existing_site_copy") or ""),
                "top_inherit": str(hearing.get("top_inherit_note") or ""),
                "page_count_declared": str(project.get("page_count_declared") or ""),
                "excluded_existing_pages": excluded_existing,
                "focus_keywords": focus_keywords,
                "tag_keywords": list(hearing.get("tag_keywords") or []),
            },
            "omitted_pages": omitted_preview,
        },
    )
    omit_blank_pages_from_blueprint(bp)
    return bp


def build_site_blueprint(hearing: dict[str, Any]) -> dict[str, Any]:
    """Route to production-type blueprint builder."""
    ptype = str(hearing.get("production_type") or "")
    if ptype == ProductionType.TYPE3_SATELLITE.value:
        return build_type3_blueprint(hearing)
    if ptype == ProductionType.TYPE2_RENEWAL.value:
        return build_type2_blueprint(hearing)
    if ptype == ProductionType.TYPE4_SATELLITE_RENEWAL.value:
        return build_type4_blueprint(hearing)
    label = str(hearing.get("production_label") or "unknown")
    return {
        "version": 2,
        "production_type": ptype or ProductionType.UNKNOWN.value,
        "production_label": label,
        "clone_mode": "not_supported_in_v2",
        "site_name": _site_name(hearing),
        "pages": [],
        "seo_pages": [],
        "tag_pages": [],
        "dynamic_references": [],
        "nav": [],
        "stats": {"content_pages": 0, "seo_pages": 0, "tag_pages": 0, "total_sections": 0},
        "ai_stages": {"planner": "unsupported", "writer": "pending"},
        "warnings": [f"Production type {label} is not supported in this lab."],
    }


def finalize_lab_blueprint(partial: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Finalize blueprint for whichever active v2 lab type is in the hearing."""
    ptype = str(hearing.get("production_type") or "")
    if ptype == ProductionType.TYPE3_SATELLITE.value:
        return finalize_type3_blueprint(partial, hearing)
    if ptype == ProductionType.TYPE2_RENEWAL.value:
        return finalize_type2_blueprint(partial, hearing)
    if ptype == ProductionType.TYPE4_SATELLITE_RENEWAL.value:
        return finalize_type4_blueprint(partial, hearing)
    return partial


def is_v2_lab_type(hearing: dict[str, Any] | None) -> bool:
    return str((hearing or {}).get("production_type") or "") in V2_LAB_ACTIVE_TYPES
