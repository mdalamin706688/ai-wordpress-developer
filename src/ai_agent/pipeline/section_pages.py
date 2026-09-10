"""Build TOP + Service section maps from hearing (+ optional AI copy).

These attach to WordPress draft pages so checklist tabs become real page structure.
Closed-world: hearing facts only. Optional sections stay disabled when missing.
"""

from __future__ import annotations

from typing import Any

from ai_agent.pipeline.claims import freeze_missing, missing_notice
from ai_agent.pipeline.prompt_rules import (
    ACCESS_SECTION_ITEMS,
    BLOG_SECTION_ITEMS,
    COLUMN_SECTION_ITEMS,
    CONCEPT_SECTION_ITEMS,
    FAQ_SECTION_ITEMS,
    FEATURE_SECTION_ITEMS,
    GREETING_SECTION_ITEMS,
    MENU_SECTION_ITEMS,
    REVIEWS_SECTION_ITEMS,
    SERVICE_SECTION_ITEMS,
    TOP_SECTION_ITEMS,
)


def _s(value: Any) -> str:
    return str(value or "").strip()


def _menu(hearing: dict[str, Any]) -> list[dict[str, str]]:
    raw = hearing.get("menu") or []
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            name = _s(row.get("name"))
            if not name:
                continue
            out.append(
                {
                    "name": name,
                    "duration": _s(row.get("duration")),
                    "price": _s(row.get("price")),
                }
            )
    return out


def _has_staff(hearing: dict[str, Any]) -> bool:
    for key in ("staff", "staff_name", "therapist", "greeting"):
        if _s(hearing.get(key)):
            return True
    return False


def _has_reviews(hearing: dict[str, Any]) -> bool:
    reviews = hearing.get("reviews")
    if isinstance(reviews, list) and reviews:
        return True
    return bool(_s(hearing.get("reviews")))


def _missing_has(hearing: dict[str, Any], label: str) -> bool:
    return any(label in item for item in freeze_missing(hearing))


def _ai_paras(copy: dict[str, Any] | None) -> list[str]:
    if not copy:
        return []
    paras = copy.get("body_paragraphs")
    if not isinstance(paras, list):
        return []
    return [_s(p) for p in paras if _s(p)]


def build_top_sections(
    hearing: dict[str, Any],
    copy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured TOP sections for the home page (model-site order)."""
    copy = copy or {}
    name = _s(hearing.get("business_name")) or "Untitled"
    catch = _s(hearing.get("catchcopy")) or _s(copy.get("heading"))
    concept = _s(hearing.get("concept"))
    target = _s(hearing.get("target"))
    station = _s(hearing.get("station"))
    address = _s(hearing.get("address"))
    phone = _s(hearing.get("phone"))
    hours = _s(hearing.get("hours"))
    closed = _s(hearing.get("closed"))
    payment = _s(hearing.get("payment"))
    parking = _s(hearing.get("parking"))
    reservation = _s(hearing.get("reservation"))
    menu = _menu(hearing)
    paras = _ai_paras(copy)
    cta = _s(copy.get("cta")) or "ご予約はこちら"

    greeting_on = _has_staff(hearing) and not _missing_has(hearing, "スタッフ紹介")
    reviews_on = _has_reviews(hearing) and not _missing_has(hearing, "お客様の声")

    about_body = concept
    if paras and concept and concept in paras[0]:
        about_body = paras[0]
    elif paras and not concept:
        about_body = paras[0]

    points: list[dict[str, str]] = []
    if concept:
        points.append({"title": "当店の考え方", "body": concept})
    if target:
        points.append({"title": "こんな方へ", "body": target})
    if station:
        points.append({"title": "通いやすさ", "body": f"{station}の立地です。"})

    return {
        "page": "top",
        "checklist": [dict(i) for i in TOP_SECTION_ITEMS],
        "hero": {
            "brand_name": name,
            "catchcopy": catch,
            "subcopy": _s(copy.get("lead")),
            "cta": cta,
        },
        "about": {"heading": "当店について", "body": about_body},
        "concept": {
            "heading": "コンセプト",
            "lead": concept,
            "points": points[:3],
        },
        "greeting": {
            "enabled": greeting_on,
            "body": _s(hearing.get("greeting")) if greeting_on else "",
            "reason_if_disabled": "" if greeting_on else "スタッフ紹介は要ヒアリング",
        },
        "menu": {"heading": "メニュー", "items": menu},
        "access": {
            "heading": station or "アクセス",
            "station": station,
            "address": address,
            "phone": phone,
            "hours": hours,
            "closed": closed,
            "payment": payment,
            "parking": parking,
        },
        "reviews": {
            "enabled": reviews_on,
            "items": list(hearing.get("reviews") or []) if reviews_on else [],
            "reason_if_disabled": "" if reviews_on else "お客様の声は要ヒアリング",
        },
        "reservation": {
            "heading": "ご予約お待ちしております。",
            "cta": cta,
            "phone": phone,
            "hours": hours,
            "method": reservation,
        },
        "qa": {
            "missing": freeze_missing(hearing),
            "missing_notice": missing_notice(freeze_missing(hearing)),
        },
    }


def build_service_sections(
    hearing: dict[str, Any],
    copy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured Service page sections (model-site /service/)."""
    copy = copy or {}
    name = _s(hearing.get("business_name")) or "Untitled"
    concept = _s(hearing.get("concept"))
    phone = _s(hearing.get("phone"))
    hours = _s(hearing.get("hours"))
    cta = _s(copy.get("cta")) or "ご予約はこちら"
    menu = _menu(hearing)
    paras = _ai_paras(copy)

    services: list[dict[str, Any]] = []
    for i, item in enumerate(menu):
        detail = "、".join(p for p in (item.get("duration"), item.get("price")) if p)
        body = f"{item['name']}（{detail}）。" if detail else f"{item['name']}のご案内です。"
        # Prefer AI paragraph that mentions this menu name.
        for para in paras:
            if item["name"] in para:
                body = para
                break
        services.append(
            {
                "id": f"service_{i + 1}",
                "heading": item["name"],
                "body": body,
                "duration": item.get("duration") or "",
                "price": item.get("price") or "",
            }
        )

    lead_body = paras[0] if paras else (concept or "ヒアリングシート記載のサービスをご案内します。")
    return {
        "page": "service",
        "checklist": [dict(i) for i in SERVICE_SECTION_ITEMS],
        "hero": {
            "heading": _s(copy.get("heading")) or "サービス",
            "lead": _s(copy.get("lead")) or "提供サービス",
            "body": lead_body,
        },
        "services": services,
        "reservation": {
            "heading": "ご予約お待ちしております。",
            "cta": cta,
            "phone": phone,
            "hours": hours,
        },
        "seo_title": _s(copy.get("title")) or f"サービス｜{name}",
        "qa": {
            "missing": freeze_missing(hearing),
            "missing_notice": missing_notice(freeze_missing(hearing)),
        },
    }


def build_section_bundle(
    hearing: dict[str, Any],
    copy: dict[str, Any] | None = None,
    *,
    page: str = "top",
) -> dict[str, Any]:
    """Build section maps for every static header page (hearing + optional AI copies)."""
    copy = copy or {}
    page_copies = copy.get("_page_copies") if isinstance(copy.get("_page_copies"), dict) else {}
    if not isinstance(page_copies, dict):
        page_copies = {}
    # Back-compat: dual TOP/Service merge stored service under _service_copy.
    if copy.get("_service_copy") and "service" not in page_copies:
        page_copies = {**page_copies, "service": copy.get("_service_copy")}
    key = (page or "top").strip().lower()
    if key in {"home", ""}:
        key = "top"
    def _copy_for(pid: str) -> dict[str, Any] | None:
        if pid in page_copies and isinstance(page_copies[pid], dict):
            return page_copies[pid]
        if key == pid:
            return copy
        return None

    return {
        "top": build_top_sections(hearing, _copy_for("top")),
        "concept": build_concept_sections(hearing, _copy_for("concept")),
        "service": build_service_sections(hearing, _copy_for("service")),
        "greeting": build_greeting_sections(hearing, _copy_for("greeting")),
        "menu": build_menu_sections(hearing, _copy_for("menu")),
        "faq": build_faq_sections(hearing, _copy_for("faq")),
        "feature": build_feature_sections(hearing, _copy_for("feature")),
        "access": build_access_sections(hearing, _copy_for("access")),
        "blog": build_blog_sections(hearing, None),
        "column": build_column_sections(hearing, None),
        "reviews": build_reviews_sections(hearing, _copy_for("reviews")),
    }


def build_concept_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    concept = _s(hearing.get("concept"))
    target = _s(hearing.get("target"))
    paras = _ai_paras(copy)
    points: list[dict[str, str]] = []
    if concept:
        points.append({"title": "当店の考え方", "body": concept})
    if target:
        points.append({"title": "こんな方へ", "body": target})
    tone = _s(hearing.get("tone")) or _s(hearing.get("atmosphere"))
    if tone:
        points.append({"title": "雰囲気", "body": tone})
    return {
        "page": "concept",
        "checklist": [dict(i) for i in CONCEPT_SECTION_ITEMS],
        "hero": {
            "heading": _s(copy.get("heading")) or "コンセプト",
            "lead": _s(copy.get("lead")) or concept,
            "body": paras[0] if paras else concept,
        },
        "points": {"heading": "コンセプト", "items": points[:3]},
        "cta": {"cta": _s(copy.get("cta")) or "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def build_greeting_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    enabled = _has_staff(hearing) and not _missing_has(hearing, "スタッフ紹介")
    body = _s(hearing.get("greeting")) or _s(hearing.get("staff")) or _s(hearing.get("staff_name"))
    paras = _ai_paras(copy)
    return {
        "page": "greeting",
        "checklist": [dict(i) for i in GREETING_SECTION_ITEMS],
        "enabled": enabled,
        "hero": {
            "heading": _s(copy.get("heading")) or "ご挨拶",
            "lead": _s(copy.get("lead")) if enabled else "",
            "enabled": enabled,
        },
        "message": {
            "enabled": enabled,
            "body": (paras[0] if paras else body) if enabled else "",
            "reason_if_disabled": "" if enabled else "スタッフ紹介は要ヒアリング",
        },
        "cta": {"cta": _s(copy.get("cta")) or "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def build_menu_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    menu = _menu(hearing)
    paras = _ai_paras(copy)
    return {
        "page": "menu",
        "checklist": [dict(i) for i in MENU_SECTION_ITEMS],
        "hero": {
            "heading": _s(copy.get("heading")) or "メニュー",
            "lead": _s(copy.get("lead")) or "所要時間と料金はヒアリングシートの記載です。",
            "body": paras[0] if paras else "",
        },
        "items": {"heading": "メニュー", "items": menu},
        "notes": {"body": _s(copy.get("notes"))},
        "cta": {"cta": _s(copy.get("cta")) or "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def build_faq_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    paras = _ai_paras(copy)
    items: list[dict[str, str]] = []
    # Deterministic FAQ seeds from hearing facts only (AI may expand in paras).
    if _s(hearing.get("hours")):
        items.append({"q": "営業時間は？", "a": _s(hearing.get("hours")) + (f"（{_s(hearing.get('closed'))}）" if _s(hearing.get("closed")) else "")})
    if _s(hearing.get("station")):
        items.append({"q": "アクセスは？", "a": _s(hearing.get("station"))})
    if _s(hearing.get("reservation")) or _s(hearing.get("phone")):
        items.append({"q": "予約方法は？", "a": _s(hearing.get("reservation")) or f"お電話（{_s(hearing.get('phone'))}）"})
    if _menu(hearing):
        names = "、".join(i["name"] for i in _menu(hearing)[:4])
        items.append({"q": "メニューは？", "a": f"{names}などをご用意しています。料金はメニューページをご確認ください。"})
    return {
        "page": "faq",
        "checklist": [dict(i) for i in FAQ_SECTION_ITEMS],
        "hero": {
            "heading": _s(copy.get("heading")) or "よくある質問",
            "lead": _s(copy.get("lead")) or "ヒアリングシートの事実に基づくご案内です。",
            "body": paras[0] if paras else "",
        },
        "items": {"heading": "Q&A", "items": items[:6]},
        "cta": {"cta": _s(copy.get("cta")) or "お問い合わせはこちら", "phone": _s(hearing.get("phone"))},
    }


def build_feature_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    concept = _s(hearing.get("concept"))
    target = _s(hearing.get("target"))
    atmosphere = _s(hearing.get("atmosphere")) or _s(hearing.get("tone"))
    paras = _ai_paras(copy)
    points: list[dict[str, str]] = []
    if concept:
        points.append({"title": "こだわり", "body": concept})
    if target:
        points.append({"title": "対象の方", "body": target})
    if atmosphere:
        points.append({"title": "空間・雰囲気", "body": atmosphere})
    return {
        "page": "feature",
        "checklist": [dict(i) for i in FEATURE_SECTION_ITEMS],
        "hero": {
            "heading": _s(copy.get("heading")) or "特徴",
            "lead": _s(copy.get("lead")) or concept,
            "body": paras[0] if paras else concept,
        },
        "points": {"heading": "特徴", "items": points[:3]},
        "cta": {"cta": _s(copy.get("cta")) or "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def build_access_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    paras = _ai_paras(copy)
    return {
        "page": "access",
        "checklist": [dict(i) for i in ACCESS_SECTION_ITEMS],
        "hero": {
            "heading": _s(copy.get("heading")) or (_s(hearing.get("station")) or "アクセス"),
            "lead": _s(copy.get("lead")) or _s(hearing.get("station")),
            "body": paras[0] if paras else "",
        },
        "details": {
            "station": _s(hearing.get("station")),
            "address": _s(hearing.get("address")),
            "phone": _s(hearing.get("phone")),
            "hours": _s(hearing.get("hours")),
            "closed": _s(hearing.get("closed")),
            "payment": _s(hearing.get("payment")),
            "parking": _s(hearing.get("parking")),
        },
        "map": {"body": f"{_s(hearing.get('address'))} 周辺。" if _s(hearing.get("address")) else ""},
        "cta": {"cta": _s(copy.get("cta")) or "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def build_reviews_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    copy = copy or {}
    enabled = _has_reviews(hearing) and not _missing_has(hearing, "お客様の声")
    raw = hearing.get("reviews") if enabled else []
    items = list(raw) if isinstance(raw, list) else ([_s(raw)] if _s(raw) else [])
    return {
        "page": "reviews",
        "checklist": [dict(i) for i in REVIEWS_SECTION_ITEMS],
        "enabled": enabled,
        "hero": {
            "heading": _s(copy.get("heading")) or "お客様の声",
            "lead": _s(copy.get("lead")) if enabled else "",
            "enabled": enabled,
            "reason_if_disabled": "" if enabled else "お客様の声は要ヒアリング",
        },
        "items": {"enabled": enabled, "items": items if enabled else [], "reason_if_disabled": "" if enabled else "お客様の声は要ヒアリング"},
        "cta": {"cta": _s(copy.get("cta")) or "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def build_blog_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    name = _s(hearing.get("business_name")) or "当店"
    return {
        "page": "blog",
        "checklist": [dict(i) for i in BLOG_SECTION_ITEMS],
        "shell": True,
        "hero": {
            "heading": "ブログ",
            "lead": f"{name}のブログ一覧です。個別記事はCMS側で更新します（AIは記事を作成しません）。",
            "body": "",
        },
        "cta": {"cta": "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def build_column_sections(hearing: dict[str, Any], copy: dict[str, Any] | None = None) -> dict[str, Any]:
    name = _s(hearing.get("business_name")) or "当店"
    return {
        "page": "column",
        "checklist": [dict(i) for i in COLUMN_SECTION_ITEMS],
        "shell": True,
        "hero": {
            "heading": "コラム",
            "lead": f"{name}のコラム一覧です。個別コラムはCMS側で更新します（AIは記事を作成しません）。",
            "body": "",
        },
        "cta": {"cta": "ご予約はこちら", "phone": _s(hearing.get("phone"))},
    }


def merge_top_service_copies(
    hearing: dict[str, Any],
    top_copy: dict[str, Any],
    service_copy: dict[str, Any],
) -> dict[str, Any]:
    """Back-compat wrapper → full header merge with TOP + Service AI copies."""
    return merge_header_page_copies(
        hearing,
        {"top": top_copy, "service": service_copy},
    )


def merge_header_page_copies(
    hearing: dict[str, Any],
    page_copies: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Combine AI page drafts for all static header pages into one package copy."""
    from ai_agent.pipeline.section_enforce import section_coverage_issues

    page_copies = {str(k): dict(v or {}) for k, v in (page_copies or {}).items()}
    top_copy = page_copies.get("top") or {}
    out = dict(top_copy)
    out["_page"] = "top"
    out["_page_copies"] = page_copies
    if page_copies.get("service"):
        out["_service_copy"] = page_copies["service"]
    # Seed builders with attached copies.
    seed = dict(out)
    seed["_page_copies"] = page_copies
    bundle = build_section_bundle(hearing, seed, page="top")
    out["_sections"] = bundle
    gaps: list[dict[str, str]] = []
    for pid, blob in page_copies.items():
        gaps.extend(section_coverage_issues(blob, hearing, page=pid))
    out["_section_gaps"] = gaps
    warnings = list(out.get("_qa_warnings") or [])
    for gap in gaps:
        tip = str(gap.get("suggestion") or "").strip()
        if tip and tip not in warnings:
            warnings.append(tip)
    out["_qa_warnings"] = warnings
    notes: list[str] = []
    for blob in page_copies.values():
        note = str(blob.get("notes") or "").strip()
        if note and note not in notes:
            notes.append(note)
    if notes:
        out["notes"] = " / ".join(notes)
    return out
