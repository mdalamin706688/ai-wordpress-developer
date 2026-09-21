"""Fill nested fact blocks from hearing (no invention)."""

from __future__ import annotations

import re
from typing import Any

_BRAND_ORIGIN_MARKERS = ("太陽さん", "名前になりました", "天気と付き合う")
_LONG_CATCH_MARKERS = ("請け負う会社", "という名前", "を中心に、", "心を込めて塗装")


def _s(value: Any) -> str:
    return str(value or "").strip()


def default_cta_label(hearing: dict[str, Any]) -> str:
    """Inquiry CTA label for lead_gen / service when AI left label empty."""
    try:
        from ai_agent.v2.site_category import derive_site_category

        cat = _s(derive_site_category(hearing).get("category"))
    except Exception:
        cat = ""
    if cat in {"lead_gen", "service"}:
        return "無料相談・お見積りはこちら"
    if cat == "recruit":
        return "採用について問い合わせる"
    methods = hearing_reservation_methods(hearing)
    if methods:
        return "お問い合わせはこちら"
    return ""


def _first_selling_sentence(hearing: dict[str, Any]) -> str:
    wg = hearing.get("writing_guidance") if isinstance(hearing.get("writing_guidance"), dict) else {}
    raw = _s(wg.get("selling_points"))
    for m in re.finditer(r"\[([^\]]+)\]", raw):
        body = _s(m.group(1))
        if not body:
            continue
        # Prefer brand-origin / concept sentences for short_description.
        if any(x in body for x in _BRAND_ORIGIN_MARKERS) or "島原" in body or "塗装" in body:
            sent = body.split("。")[0].strip()
            return (sent + "。") if sent and not sent.endswith("。") else sent
    return ""


def hearing_support_blurb(hearing: dict[str, Any]) -> str:
    """1–2 sentence support line from 売り brackets (for short_description)."""
    return _first_selling_sentence(hearing)


def _catchphrase_fallback(hearing: dict[str, Any]) -> str:
    project = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    area = _s(project.get("area"))
    industry = _s(project.get("industry"))
    candidates: list[str] = []
    if area and industry:
        candidates.extend(
            [
                f"{area}の{industry}",
                f"{area}で安心の{industry}",
                f"{area}の住まいを守る{industry}",
                f"{area}の{industry}はお任せください",
            ]
        )
    elif industry:
        candidates.append(industry)
    elif area:
        candidates.append(f"{area}の専門店")
    for c in candidates:
        n = len(c)
        if 15 <= n <= 28:
            return c
    for c in candidates:
        if c and len(c) <= 28:
            return c
    return (candidates[0][:28] if candidates else "")


def normalize_catchphrase(text: str, hearing: dict[str, Any]) -> str:
    """Keep punchy 15–28字 catchphrases; rebuild long corporate dumps from area+industry."""
    t = _s(text)
    if t and 15 <= len(t) <= 28 and "。" not in t and not any(m in t for m in _LONG_CATCH_MARKERS):
        return t
    if t and len(t) <= 28 and "。" not in t and not any(m in t for m in _LONG_CATCH_MARKERS):
        # Short but usable AI line — keep if at least ~10 chars.
        if len(t) >= 10:
            return t
    # Try first sentence / clause if AI wrote a long dump.
    if t:
        head = t.split("。", 1)[0].strip()
        if 15 <= len(head) <= 28 and not any(m in head for m in _LONG_CATCH_MARKERS):
            return head
    return _catchphrase_fallback(hearing)


def shorten_catchcopy(text: str, hearing: dict[str, Any]) -> str:
    """Back-compat alias — prefer normalize_catchphrase."""
    t = _s(text)
    if t and len(t) <= 32 and "。" not in t and not any(m in t for m in _LONG_CATCH_MARKERS):
        # Still nudge into emotional 15–28 when possible via normalize.
        return normalize_catchphrase(t, hearing)
    return normalize_catchphrase(t, hearing)


def hearing_hours(hearing: dict[str, Any]) -> str:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    open_h = _s(store.get("hours_open"))
    close_h = _s(store.get("hours_close"))
    note = _s(store.get("hours_note"))
    if open_h and close_h:
        base = f"{open_h}–{close_h}"
        return f"{base}（{note}）" if note else base
    return note


def hearing_payment(hearing: dict[str, Any]) -> str:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    other = _s(store.get("other"))
    if "支払" in other or "クレジット" in other or "現金" in other:
        lines = [ln.strip() for ln in other.splitlines() if ln.strip()]
        pay_lines = [ln for ln in lines if "支払" in ln or "クレジット" in ln or "現金" in ln or "振込" in ln]
        if pay_lines:
            body = [ln for ln in pay_lines if not ln.startswith("■")]
            return " / ".join(body) if body else pay_lines[-1].lstrip("■").strip()
    wg = hearing.get("writing_guidance") if isinstance(hearing.get("writing_guidance"), dict) else {}
    price = _s(wg.get("price_notes"))
    if "カード" in price:
        return price
    return ""


def hearing_business_name(hearing: dict[str, Any]) -> str:
    project = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    return _s(project.get("business_name")) or _s(store.get("name"))


def hearing_line_url(hearing: dict[str, Any]) -> str:
    wg = hearing.get("writing_guidance") if isinstance(hearing.get("writing_guidance"), dict) else {}
    return _s(wg.get("cv_destination"))


def hearing_service_names(hearing: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for slot in hearing.get("pages") or []:
        if not isinstance(slot, dict):
            continue
        if "サービス" not in _s(slot.get("type")):
            continue
        for item in slot.get("items") or []:
            t = _s(item)
            if t:
                out.append(t)
    return out


def hearing_reservation_methods(hearing: dict[str, Any]) -> list[str]:
    wg = hearing.get("writing_guidance") if isinstance(hearing.get("writing_guidance"), dict) else {}
    raw = wg.get("reservation_methods")
    if isinstance(raw, list):
        return [_s(x) for x in raw if _s(x)]
    text = _s(raw)
    if not text:
        return []
    parts = re.split(r"[、,，/｜|]", text)
    return [p.strip() for p in parts if p.strip()]


def _nested_business_info(hearing: dict[str, Any]) -> dict[str, str]:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    return {
        "name": hearing_business_name(hearing),
        "postal": _s(store.get("postal")),
        "address": _s(store.get("address")),
        "phone": _s(store.get("phone")),
        "hours": hearing_hours(hearing),
        "closed": _s(store.get("closed")),
        "payment": hearing_payment(hearing),
        "email": _s(store.get("email")),
        "instagram": _s(store.get("instagram") or store.get("instagram_url")),
    }


def _nested_cta(hearing: dict[str, Any]) -> dict[str, str]:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    phone = _s(store.get("phone"))
    line = hearing_line_url(hearing)
    methods = hearing_reservation_methods(hearing)
    return {
        "label": default_cta_label(hearing),
        "phone": phone,
        "url": line,
        "line_url": line,
        "methods": "\n".join(methods),
    }


def _nested_access_details(hearing: dict[str, Any]) -> dict[str, str]:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    addr = _s(store.get("address"))
    return {
        "station": _s(store.get("station")),
        "address": addr,
        "phone": _s(store.get("phone")),
        "hours": hearing_hours(hearing),
        "closed": _s(store.get("closed")),
        "payment": hearing_payment(hearing),
        "parking": _s(store.get("parking")),
        "map_note": f"所在地: {addr}" if addr else "",
        "map_url": _s(store.get("map_url")),
    }


def _nested_contact_details(hearing: dict[str, Any]) -> dict[str, str]:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    line = hearing_line_url(hearing)
    methods = hearing_reservation_methods(hearing)
    return {
        "phone": _s(store.get("phone")),
        "email": _s(store.get("email")),
        "methods": "\n".join(methods),
        "hours": hearing_hours(hearing),
        "line_url": line,
        "instagram": _s(store.get("instagram") or store.get("instagram_url")),
        "form_note": "",
    }


def fact_value_for_slot(
    section_id: str,
    hearing: dict[str, Any],
    page: dict[str, Any] | None = None,
) -> str | None:
    """Return exact hearing value for a flat fact slot, or None."""
    sid = _s(section_id)
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    page = page or {}
    name = hearing_business_name(hearing)
    phone = _s(store.get("phone"))
    address = _s(store.get("address"))
    postal = _s(store.get("postal"))
    closed = _s(store.get("closed"))
    hours = hearing_hours(hearing)
    payment = hearing_payment(hearing)
    line = hearing_line_url(hearing)
    email = _s(store.get("email"))
    instagram = _s(store.get("instagram") or store.get("instagram_url"))
    focus = [_s(k) for k in (hearing.get("focus_keywords") or []) if _s(k)]
    services = hearing_service_names(hearing)
    methods = hearing_reservation_methods(hearing)

    exact: dict[str, str] = {
        "hero_brand_name": name,
        "business_info_name": name,
        "business_info_postal": postal,
        "business_info_address": address,
        "business_info_phone": phone,
        "cta_phone": phone,
        "details_phone": phone,
        "business_info_hours": hours,
        "details_hours": hours,
        "business_info_closed": closed,
        "details_closed": closed,
        "business_info_payment": payment,
        "details_payment": payment,
        "business_info_email": email,
        "details_email": email,
        "business_info_instagram": instagram,
        "details_instagram": instagram,
        "hero_cta_url": line,
        "cta_line_url": line,
        "cta_url": line,
        "details_line_url": line,
        "details_address": address,
        "details_station": _s(store.get("station")),
        "details_parking": _s(store.get("parking")),
        "map_url": _s(store.get("map_url")),
        "hero_focus_keywords": "\n".join(focus),
        "services_teaser_items": "\n".join(services),
        "cta_methods": "\n".join(methods),
        "reference_url": _s(page.get("reference_url")),
        "keyword": _s(page.get("seo_primary_keyword") or page.get("tag_keyword") or ""),
    }
    if sid in exact:
        return exact[sid]
    return None


def sanitize_map_note(text: str, hearing: dict[str, Any]) -> str:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    addr = _s(store.get("address"))
    t = _s(text)
    if any(m in t for m in _BRAND_ORIGIN_MARKERS):
        return f"所在地: {addr}" if addr else ""
    map_hints = ("地図", "住所", "アクセス", "所在", "駅", "駐車場", "Google")
    if t and not any(h in t for h in map_hints):
        return f"所在地: {addr}" if addr else ""
    return t


def _merge_nested_facts(current: Any, forced: dict[str, str]) -> dict[str, str]:
    out = dict(forced)
    if isinstance(current, dict):
        for key, val in current.items():
            sk = str(key)
            if sk not in out:
                out[sk] = _s(val)
            elif sk in {"label", "form_note", "catchphrase", "short_description", "heading", "lead", "body"}:
                # keep AI-2 composed fields unless forced is non-empty and field is exact-fact
                if sk in forced and forced[sk]:
                    # Prefer AI label when present; fill from forced only if AI empty.
                    if sk == "label":
                        out[sk] = _s(val) or forced[sk]
                    else:
                        out[sk] = forced[sk]
                else:
                    out[sk] = _s(val) if _s(val) else forced.get(sk, "")
            else:
                # exact fact keys always overwrite from hearing
                out[sk] = forced.get(sk, _s(val))
    return out


def _normalize_catchphrase_block(
    block: Any,
    hearing: dict[str, Any],
    *,
    with_brand: bool,
) -> dict[str, str]:
    raw = block if isinstance(block, dict) else {}
    raw_catch = _s(raw.get("catchphrase"))
    catchphrase = normalize_catchphrase(raw_catch, hearing)
    short_description = _s(raw.get("short_description"))
    if not short_description:
        # Preserve long AI/hearing story when we shortened the catchphrase.
        if raw_catch and raw_catch != catchphrase and len(raw_catch) > 28:
            short_description = raw_catch
        else:
            short_description = hearing_support_blurb(hearing)
    out: dict[str, str] = {
        "catchphrase": catchphrase,
        "short_description": short_description,
    }
    if with_brand:
        out = {
            "brand_name": hearing_business_name(hearing),
            **out,
        }
    return out


def enforce_hearing_fact_slots(
    sections: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any],
) -> dict[str, Any]:
    """Overwrite fact slots / nested fact blocks with hearing values."""
    out = dict(sections)

    nested_forced: dict[str, dict[str, str]] = {
        "business_info": _nested_business_info(hearing),
        "cta": _nested_cta(hearing),
        "access_details": _nested_access_details(hearing),
        "contact_details": _nested_contact_details(hearing),
    }
    # top / concept catchphrase: brand (TOP) + normalize length; story in short_description
    if "top_catchphrase" in out or "hero" in out:
        key = "top_catchphrase" if "top_catchphrase" in out else "hero"
        out["top_catchphrase"] = _normalize_catchphrase_block(out.get(key), hearing, with_brand=True)
        if key == "hero" and "hero" in out:
            del out["hero"]
    if "concept_catchphrase" in out:
        out["concept_catchphrase"] = _normalize_catchphrase_block(
            out.get("concept_catchphrase"), hearing, with_brand=False
        )

    for sid, forced in nested_forced.items():
        if sid not in out:
            continue
        out[sid] = _merge_nested_facts(out.get(sid), forced)
        if sid == "access_details" and isinstance(out[sid], dict):
            out[sid]["map_note"] = sanitize_map_note(_s(out[sid].get("map_note")), hearing)
        if sid == "cta" and isinstance(out[sid], dict) and not _s(out[sid].get("label")):
            out[sid]["label"] = default_cta_label(hearing)

    for sid in list(out.keys()):
        if isinstance(out.get(sid), (dict, list)):
            continue
        forced = fact_value_for_slot(sid, hearing, page)
        if forced is not None:
            out[sid] = forced
    if "hero_catchcopy" in out and isinstance(out.get("hero_catchcopy"), str):
        out["hero_catchcopy"] = normalize_catchphrase(out.get("hero_catchcopy") or "", hearing)
    if "map_note" in out and isinstance(out.get("map_note"), str):
        out["map_note"] = sanitize_map_note(out.get("map_note") or "", hearing)
    return out
