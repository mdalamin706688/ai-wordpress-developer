from __future__ import annotations

from typing import Any

from ai_agent.pipeline.claims import freeze_missing, missing_notice, missing_preserved
from ai_agent.pipeline.htmlsafe import sanitize_site_pages
from ai_agent.pipeline.section_pages import build_section_bundle


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    import re

    text = str(value or "").strip()
    if not text:
        return []
    return [
        part.strip()
        for part in re.split(r"[、;；]+|(?<!\d),(?!\d{3})", text)
        if part.strip()
    ]


def _menu(hearing: dict[str, Any]) -> list[dict[str, str]]:
    raw = hearing.get("menu") or []
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return [
            {
                "name": str(item.get("name") or ""),
                "duration": str(item.get("duration") or ""),
                "price": str(item.get("price") or ""),
            }
            for item in raw
            if item.get("name")
        ]
    return [
        {"name": name, "duration": "", "price": ""}
        for name in _list(hearing.get("services"))
    ]


def compose_site_draft(hearing: dict[str, Any], copy: dict[str, Any]) -> dict[str, Any]:
    """Deterministic WordPress draft package. Never published.

    Static header pages only (model-site gnav):
    TOP, concept, service, greeting, menu, faq, feature, access, blog, column, reviews.
    Blog/column are listing shells (no individual posts). Feature subtopics excluded.
    """
    from ai_agent.pipeline.prompt_rules import HEADER_PAGES
    from ai_agent.pipeline.section_pages import merge_header_page_copies

    copy = dict(copy or {})
    for key in ("publish_allowed", "published", "status", "human_approved", "approval"):
        copy.pop(key, None)
    name = str(hearing.get("business_name") or "Untitled")
    area = str(hearing.get("area") or "")
    address = str(hearing.get("address") or "")
    station = str(hearing.get("station") or "")
    phone = str(hearing.get("phone") or "")
    hours = str(hearing.get("hours") or "")
    closed = str(hearing.get("closed") or "")
    parking = str(hearing.get("parking") or "")
    reservation = str(hearing.get("reservation") or "")
    catchcopy = str(hearing.get("catchcopy") or "")
    missing = freeze_missing(hearing)
    colors = hearing.get("colors") or {}
    menu = _menu(hearing)

    page_intent = str(
        hearing.get("target_page")
        or copy.get("_page")
        or (copy.get("slug") if copy.get("slug") == "service" else "top")
        or "top"
    ).lower()
    if page_intent in {"home", ""}:
        page_intent = "top"

    page_copies = copy.get("_page_copies") if isinstance(copy.get("_page_copies"), dict) else {}
    if not page_copies and isinstance(copy.get("_service_copy"), dict):
        page_copies = {"top": copy, "service": copy["_service_copy"]}

    pre = copy.get("_sections") if isinstance(copy.get("_sections"), dict) else None
    if isinstance(pre, dict) and pre.get("top") and pre.get("service"):
        sections_bundle = pre
        # Fill missing header keys from builders when older dual-only bundles arrive.
        if len(sections_bundle) < 5:
            full = build_section_bundle(hearing, copy, page=page_intent)
            for k, v in full.items():
                sections_bundle.setdefault(k, v)
    elif page_copies:
        merged = merge_header_page_copies(hearing, page_copies)
        sections_bundle = merged.get("_sections") or build_section_bundle(hearing, copy, page="top")
        copy = merged
    else:
        sections_bundle = build_section_bundle(hearing, copy, page=page_intent)

    top = sections_bundle.get("top") or {}
    service = sections_bundle.get("service") or {}

    def _pc(pid: str) -> dict[str, Any]:
        blob = page_copies.get(pid) if isinstance(page_copies, dict) else None
        return blob if isinstance(blob, dict) else {}

    def _paras_from(pid: str, fallback: list[str]) -> list[str]:
        blob = _pc(pid)
        paras = list(blob.get("body_paragraphs") or [])
        if any(str(p).strip() for p in paras):
            return [str(p) for p in paras]
        if pid == "top" and page_intent == "top" and any(str(p).strip() for p in (copy.get("body_paragraphs") or [])):
            return list(copy.get("body_paragraphs") or [])
        return [p for p in fallback if str(p).strip()]

    access_lines = []
    if address:
        access_lines.append(address)
    elif area:
        access_lines.append(area)
    if station:
        access_lines.append(station)
    if hours:
        access_lines.append(f"営業時間 {hours}" + (f" / {closed}" if closed else ""))
    if parking:
        access_lines.append(f"駐車場：{parking}")

    contact_lines = []
    if phone:
        contact_lines.append(f"TEL {phone}")
    if reservation:
        contact_lines.append(f"ご予約：{reservation}")

    home_paras = _paras_from(
        "top",
        [
            str((top.get("about") or {}).get("body") or ""),
            " ".join(
                f"{i.get('name')} {i.get('duration')} {i.get('price')}".strip()
                for i in (top.get("menu") or {}).get("items") or []
            ),
            str((top.get("access") or {}).get("station") or ""),
            f"{hours} {closed} {phone}".strip(),
            str((top.get("reservation") or {}).get("method") or ""),
        ],
    )
    service_paras = _paras_from(
        "service",
        [
            str((service.get("hero") or {}).get("body") or ""),
            *[
                f"{b.get('heading') or ''}: {b.get('body') or ''}".strip(": ")
                for b in (service.get("services") or [])
                if isinstance(b, dict)
            ],
        ],
    )

    home_slug = "home"
    raw_slug = str((_pc("top").get("slug") or copy.get("slug") or "home")).strip() or "home"
    if raw_slug not in {"service", "concept", "menu", "access", "faq", "feature", "blog", "column", "reviews", "greeting"}:
        home_slug = raw_slug

    def _page_block(
        *,
        pid: str,
        slug: str,
        nav_label: str,
        title: str,
        heading: str,
        lead: str,
        body: list[str],
        sections: dict[str, Any] | None,
        items: list | None = None,
        cta: str = "",
        notes: str = "",
        photo_slots: int = 1,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": pid,
            "wp_type": "page",
            "status": "draft",
            "title": title,
            "slug": slug,
            "nav_label": nav_label,
            "heading": heading,
            "lead": lead,
            "body_paragraphs": [p for p in body if p],
            "cta": cta or "ご予約はこちら",
            "photo_slots": photo_slots,
            "notes": notes,
        }
        if sections is not None:
            out["sections"] = sections
        if items is not None:
            out["items"] = items
        return out

    top_copy = _pc("top") or (copy if page_intent == "top" else {})
    service_copy = _pc("service")

    pages: list[dict[str, Any]] = [
        _page_block(
            pid="home",
            slug=home_slug,
            nav_label="TOP",
            title=str(top_copy.get("title") or copy.get("title") or f"{name}｜トップ"),
            heading=str(top_copy.get("heading") or copy.get("heading") or catchcopy),
            lead=str(top_copy.get("lead") or copy.get("lead") or catchcopy),
            body=home_paras,
            sections=top,
            cta=str(top_copy.get("cta") or copy.get("cta") or "ご予約はこちら"),
            notes=str(top_copy.get("notes") or ""),
            photo_slots=2,
        ),
    ]

    # Remaining header pages in model-site nav order (skip top — already home).
    for meta in HEADER_PAGES:
        pid = str(meta["id"])
        if pid == "top":
            continue
        sec = sections_bundle.get(pid) if isinstance(sections_bundle.get(pid), dict) else {}
        blob = _pc(pid)
        hero = sec.get("hero") if isinstance(sec.get("hero"), dict) else {}
        nav = str(meta.get("nav_label") or meta.get("label") or pid)
        slug = str(meta.get("wp_id") or pid)
        default_title = f"{nav}｜{name}"
        if pid == "service":
            pages.append(
                _page_block(
                    pid="service",
                    slug="service",
                    nav_label=nav,
                    title=str(blob.get("title") or service.get("seo_title") or default_title),
                    heading=str(blob.get("heading") or hero.get("heading") or "サービス"),
                    lead=str(blob.get("lead") or hero.get("lead") or ""),
                    body=service_paras,
                    sections=service,
                    cta=str(blob.get("cta") or "ご予約はこちら"),
                    notes=str(blob.get("notes") or ""),
                )
            )
            continue
        if pid == "menu":
            pages.append(
                _page_block(
                    pid="menu",
                    slug="menu",
                    nav_label=nav,
                    title=str(blob.get("title") or default_title),
                    heading=str(blob.get("heading") or hero.get("heading") or "メニュー"),
                    lead=str(blob.get("lead") or hero.get("lead") or "所要時間と料金はヒアリングシートの記載です。"),
                    body=_paras_from("menu", [str(hero.get("body") or "")]),
                    sections=sec,
                    items=menu,
                    cta=str(blob.get("cta") or "ご予約はこちら"),
                    notes=str(blob.get("notes") or ""),
                )
            )
            continue
        if pid == "access":
            pages.append(
                _page_block(
                    pid="access",
                    slug="access",
                    nav_label=nav,
                    title=str(blob.get("title") or default_title),
                    heading=str(blob.get("heading") or hero.get("heading") or "アクセス"),
                    lead=str(blob.get("lead") or hero.get("lead") or station or area),
                    body=_paras_from("access", access_lines),
                    sections=sec,
                    cta=str(blob.get("cta") or "ご予約はこちら"),
                    notes=str(blob.get("notes") or ""),
                    photo_slots=0,
                )
            )
            continue
        # concept / greeting / faq / feature / blog / column / reviews
        pages.append(
            _page_block(
                pid=pid,
                slug=slug,
                nav_label=nav,
                title=str(blob.get("title") or default_title),
                heading=str(blob.get("heading") or hero.get("heading") or nav),
                lead=str(blob.get("lead") or hero.get("lead") or ""),
                body=_paras_from(pid, [str(hero.get("body") or ""), str(hero.get("lead") or "")]),
                sections=sec,
                cta=str(blob.get("cta") or "ご予約はこちら"),
                notes=str(blob.get("notes") or ""),
                photo_slots=0 if pid in {"blog", "column", "faq"} else 1,
            )
        )

    # Contact / reservation helper page (not always in gnav; keep for WP drafts).
    pages.append(
        _page_block(
            pid="contact",
            slug="contact",
            nav_label="ご予約",
            title=f"ご予約｜{name}",
            heading="ご予約・お問い合わせ",
            lead=str(copy.get("cta") or "ご予約・ご質問はお気軽にどうぞ。"),
            body=contact_lines,
            sections=None,
            cta=str(copy.get("cta") or "ご予約はこちら"),
            photo_slots=0,
        )
    )

    package = {
        "status": "draft",
        "published": False,
        "publish_allowed": False,
        "human_approved": False,
        "site_name": name,
        "theme": {
            "base": colors.get("base", "#FBF7F0"),
            "ink": colors.get("ink", "#2C2A26"),
            "accent": colors.get("accent-1", "#2a7d4f"),
            "gold": colors.get("accent-2", "#C4A574"),
        },
        "nav": [{"id": page["id"], "label": page["nav_label"], "url": f"/{page['slug']}"} for page in pages],
        "pages": pages,
        "menu": menu,
        "missing": list(missing),
        "sections": sections_bundle,
        "page_intent": page_intent,
        "copy": {
            "title": copy.get("title") or "",
            "heading": copy.get("heading") or "",
            "lead": copy.get("lead") or "",
            "body_paragraphs": copy.get("body_paragraphs") or [],
            "cta": copy.get("cta") or "",
            "notes": copy.get("notes") or "",
        },
        "qa": {
            "missing": list(missing),
            "missing_notice": missing_notice(missing),
            "warnings": list(copy.get("_qa_warnings") or []),
            "section_gaps": list(copy.get("_section_gaps") or []),
            "repairs": list(copy.get("_qa_repairs") or []),
            "verification_status": str(copy.get("_qa_status") or ""),
            "missing_items_preserved": missing_preserved(hearing, missing),
        },
        "images_required": True,
        "publish_allowed": False,
    }
    return sanitize_site_pages(package)


def job_summary(
    hearing: dict[str, Any],
    site: dict[str, Any],
    *,
    latency_ms: int,
    job_id: str,
    review: str = "approved",
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "business_name": hearing.get("business_name"),
        "pages": len(site.get("pages") or []),
        "published": False,
        "latency_ms": latency_ms,
        "review": review,
    }
