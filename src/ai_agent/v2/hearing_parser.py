"""Parse BBS production hearing CSV (1,331 columns) into structured v2 JSON."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from ai_agent.v2.production_types import ProductionType, detect_production_type


def _s(value: Any) -> str:
    return str(value or "").strip()


def _yes(value: str) -> bool:
    v = _s(value).lower()
    return v in {"はい", "yes", "有", "あり", "true", "1"}


def _parse_review_items(row: dict[str, str], *, max_items: int = 10) -> list[dict[str, Any]]:
    """口コミ表示1..10 + 口コミ表示名1..10 (page composition ② — AVA–AVT)."""
    skip_text = {"表示しない", "しない", "なし", "無し", "ない", "no", "-"}
    items: list[dict[str, Any]] = []
    for n in range(1, max_items + 1):
        text = _s(row.get(f"口コミ表示{n}"))
        display_name = _s(row.get(f"口コミ表示名{n}"))
        if text in skip_text:
            continue
        if not text and not display_name:
            continue
        items.append({"n": n, "text": text, "display_name": display_name})
    return items


def _is_recruit_kind(value: str) -> bool:
    """制作種別 contains リクルート (page composition ② — AVU)."""
    v = _s(value)
    return "リクルート" in v or "求人" in v


def _top_inherit(value: str) -> bool:
    """True only when hearing asks to inherit existing TOP (not 踏襲しない)."""
    v = _s(value)
    if not v:
        return False
    if "しない" in v or "非踏襲" in v or "踏襲無し" in v or "踏襲なし" in v:
        return False
    return v.startswith("踏襲") or "踏襲する" in v


# Local / peninsula names often appear in 売り・備考 while 地域 is prefecture-only.
_AREA_LOCAL_MARKERS = (
    "島原半島",
    "島原",
    "雲仙",
    "諫早",
    "佐世保",
    "時津",
    "長与",
    "大村",
)


def _compose_area(
    *,
    region: str,
    address: str = "",
    text_blobs: list[str] | None = None,
) -> str:
    """Build a display area like 島原半島・長崎 (not prefecture-only when hearing adds locality)."""
    region = _s(region)
    address = _s(address)
    blob = " ".join([region, address, *(_s(t) for t in (text_blobs or []) if _s(t))])

    parts: list[str] = []
    for marker in _AREA_LOCAL_MARKERS:
        if marker in blob:
            parts.append(marker)
            break

    pref = region
    if not pref:
        # Pull prefecture short name from address when 地域 cell is empty.
        m = re.search(r"([^\s　]{2,3})県", address)
        if m:
            pref = m.group(1)
    pref = pref.replace("県", "").replace("府", "").replace("都", "") if pref else ""
    # Avoid "長崎県長崎" style; keep short prefecture / city label from 地域.
    if pref and pref not in parts and not any(pref in p for p in parts):
        parts.append(pref)

    if parts:
        return "・".join(parts)
    return region or pref


def _read_csv_matrix(raw: str) -> tuple[list[str], list[str]]:
    text = str(raw or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("CSV has no data")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise ValueError("CSV needs header row + one data row")
    return rows[0], rows[1]


def _row_map(headers: list[str], values: list[str]) -> dict[str, str]:
    """Map CSV headers → values. Duplicate headers (e.g. multiple 備考) keep all non-empty cells."""
    out: dict[str, str] = {}
    for i, h in enumerate(headers):
        key = _s(h)
        if not key:
            continue
        val = values[i] if i < len(values) else ""
        val = str(val or "")
        prev = out.get(key)
        if prev is None or not str(prev).strip():
            out[key] = val
        elif val.strip() and val.strip() not in str(prev):
            out[key] = f"{prev}\n{val}"
        # else: keep prev (ignore empty duplicate or exact repeat)
    return out


def _parse_page_slots(row: dict[str, str], *, max_slots: int = 20) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for n in range(1, max_slots + 1):
        ptype = _s(row.get(f"ページの追加{n} (タイプ)"))
        if not ptype:
            continue
        items: list[str] = []
        for m in range(1, 16):
            val = _s(row.get(f"ページの追加{n} (項目内容{m})"))
            if val:
                items.append(val)
        pages.append(
            {
                "slot": n,
                "label": _s(row.get(f"ページの追加{n} (表示名)")),
                "type": ptype,
                "slug": _s(row.get(f"ページの追加{n} (スラッグ)")) or _slugify(ptype),
                "url": _s(row.get(f"ページの追加{n} (URL)")),
                "items": items,
            }
        )
    return pages


def _slugify(text: str) -> str:
    t = _s(text).lower()
    if re.match(r"^[a-z0-9_-]+$", t):
        return t
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "page"


def _parse_seo_pages(row: dict[str, str], *, max_pages: int = 15) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in range(1, max_pages + 1):
        prefix = f"SEOページ{n}"
        overview = _s(row.get(f"{prefix}(概要)"))
        sections: dict[str, dict[str, str]] = {}
        for part in ("冒頭", "推1", "推2", "まとめ"):
            instr = _s(row.get(f"{prefix} ({part}指示)"))
            body = _s(row.get(f"{prefix} ({part}内容)"))
            if instr or body:
                sections[part] = {"指示": instr, "内容": body}
        if overview or sections:
            out.append({"n": n, "overview": overview, "sections": sections})
    return out


def _parse_tag_pages(row: dict[str, str], *, max_pages: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in range(1, max_pages + 1):
        instr = _s(row.get(f"タグページ{n} (指示)"))
        body = _s(row.get(f"タグページ{n} (内容)"))
        if instr or body:
            out.append({"n": n, "指示": instr, "内容": body})
    return out


def _parse_dynamic_pages(row: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in range(1, 6):
        url = _s(row.get(f"その他の動的ページURL {n}" if n > 1 else "その他の動的ページURL 1"))
        if not url and n > 1:
            url = _s(row.get(f"その他の動的ページURL {n}"))
        if not url:
            continue
        block = {
            "n": n,
            "url": url,
            "existing": _s(row.get(f"動的ページURL{n} (既存)")),
            "page_name": _s(row.get(f"動的ページURL{n} (ページ名)")),
            "required": _s(row.get(f"動的ページURL{n} (必要有無)")),
        }
        out.append(block)
    return out


def _parse_reference_sites(row: dict[str, str], *, max_sites: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in range(1, max_sites + 1):
        url = _s(row.get(f"参考サイト{n} (URL)"))
        if not url:
            continue
        out.append(
            {
                "n": n,
                "url": url,
                "kind": _s(row.get(f"参考サイト{n} (種別)")),
                "note": _s(row.get(f"参考サイト{n} (備考)")),
                "presenter": _s(row.get(f"参考サイト{n} (提示者)")),
            }
        )
    return out


def _parse_focus_keywords(row: dict[str, str], *, max_keywords: int = 5) -> list[str]:
    out: list[str] = []
    for n in range(1, max_keywords + 1):
        kw = _s(row.get(f"重点ワード{n} (ワード)"))
        if kw:
            out.append(kw)
    return out


def _parse_tag_keywords(row: dict[str, str], *, max_keywords: int = 10) -> list[str]:
    out: list[str] = []
    for n in range(1, max_keywords + 1):
        kw = _s(row.get(f"タグワード{n}"))
        if kw:
            out.append(kw)
    return out


def _parse_store(row: dict[str, str]) -> dict[str, Any]:
    return {
        "name": _s(row.get("単独店舗 (名称)") or row.get("契約企業名 or 屋号")),
        "postal": _s(row.get("単独店舗 (郵便番号)")),
        "address": _s(row.get("単独店舗 (住所)")),
        "phone": _s(row.get("単独店舗 (電話番号)")),
        "fax": _s(row.get("単独店舗 (FAX番号)")),
        "hours_open": _s(row.get("単独店舗 (始業時間)")),
        "hours_close": _s(row.get("単独店舗 (就業時間)")),
        "closed": _s(row.get("単独店舗 (定休日)")),
        "hours_note": _s(row.get("単独店舗 (営業日・定休日備考)")),
        "other": _s(row.get("単独店舗 (その他)")),
    }


def _parse_existing_pages(row: dict[str, str], *, max_pages: int = 50) -> list[dict[str, Any]]:
    """既存ページURL1..N — renewal source pages (必要 / 除外)."""
    out: list[dict[str, Any]] = []
    for n in range(1, max_pages + 1):
        name = _s(row.get(f"既存ページURL{n} (ページ名)"))
        url = _s(row.get(f"既存ページURL{n} (URL)"))
        if not name and not url:
            continue
        out.append(
            {
                "n": n,
                "page_name": name,
                "url": url,
                "existing": _s(row.get(f"既存ページURL{n} (既存)")),
                "page_kind": _s(row.get(f"既存ページURL{n} (既存ページ)")),
                "required": _s(row.get(f"既存ページURL{n} (必要有無)")),
            }
        )
    return out


def _parse_named_url_slots(
    row: dict[str, str],
    *,
    prefix: str,
    existing_suffix: str,
    max_slots: int = 5,
) -> list[dict[str, Any]]:
    """Parse フォームURL / アクセスURL / ブログURL detail blocks used by renewal."""
    out: list[dict[str, Any]] = []
    for n in range(1, max_slots + 1):
        name = _s(row.get(f"{prefix}{n} (ページ名)"))
        url = _s(row.get(f"{prefix}{n} (URL)")) or _s(row.get(f"{prefix}{n}"))
        if not name and not url:
            continue
        out.append(
            {
                "n": n,
                "page_name": name,
                "url": url,
                "existing": _s(row.get(f"{prefix}{n} (既存)")),
                "kind": _s(row.get(f"{prefix}{n} ({existing_suffix})")),
                "required": _s(row.get(f"{prefix}{n} (必要有無)")),
            }
        )
    return out


def parse_hearing_sheet(raw: str) -> dict[str, Any]:
    """Full parse of one BBS hearing row → v2 hearing document."""
    headers, values = _read_csv_matrix(raw)
    row = _row_map(headers, values)
    production_raw = _s(row.get("制作タイプ"))
    ptype = detect_production_type(production_raw)

    flags = {
        "blog": _yes(row.get("ブログはありますか")),
        "access_page": _yes(row.get("アクセスページはありますか")),
        "form": _yes(row.get("フォームはありますか")),
        "sitemap": _yes(row.get("サイトマップはありますか")),
        "dynamic": _yes(row.get("その他の動的ページはありますか")),
        "top_inherit": _top_inherit(row.get("TOP踏襲")),
    }

    review_items = _parse_review_items(row)
    production_kind = _s(row.get("制作種別"))
    ai_support_raw = _s(row.get("AIサポート"))
    # page composition ② conditionals
    flags["include_reviews"] = bool(review_items)
    flags["include_recruit"] = _is_recruit_kind(production_kind)
    flags["include_ai_blog"] = _yes(ai_support_raw)

    blog_urls = [_s(row.get(f"ブログURL{i}")) for i in range(1, 6)]
    blog_urls = [u for u in blog_urls if u]

    writing_guidance = {
        "remarks": _s(row.get("備考")),
        "writing_notes": _s(row.get("ライティング備考")),
        "selling_points": _s(row.get("売り")),
        "atmosphere": _s(row.get("雰囲気")),
        "reservation_flow": _s(row.get("来店時の予約")),
        "reservation_methods": _s(row.get("予約方法")),
        "cv_destination": _s(row.get("CV先")),
        "price_notes": _s(row.get("価格")),
        "facility_notes": _s(row.get("施設")),
        "hours_reservation": _s(row.get("営業時間・予約")),
        "content_style": _s(row.get("内容の傾向")),
        "writing_tone": _s(row.get("文章の柔らかさ")),
        "writing_perspective": _s(row.get("文章の視点")),
        "ng_tone": _s(row.get("ライティングNGテイスト")),
        "writing_days": _s(row.get("ライティング日数")),
    }

    store = _parse_store(row)
    composed_area = _compose_area(
        region=_s(row.get("地域")),
        address=_s(store.get("address")),
        text_blobs=[
            writing_guidance.get("selling_points") or "",
            writing_guidance.get("writing_notes") or "",
            writing_guidance.get("remarks") or "",
        ],
    )

    hearing: dict[str, Any] = {
        "version": 2,
        "production_type": ptype.value,
        "production_label": production_raw,
        "writing_guidance": writing_guidance,
        "project": {
            "business_name": _s(row.get("契約企業名 or 屋号")),
            "model": _s(row.get("制作モデル")),
            "store_count": _s(row.get("店舗数")),
            "page_count_declared": _s(row.get("(2)ページ数")),
            "domain": _s(row.get("公開ドメイン")),
            "existing_url": _s(row.get("既存URL")),
            "existing_site_colors": _s(row.get("既存サイト色味")),
            "existing_site_copy": _s(row.get("既存サイト文言")),
            "purpose": _s(row.get("サイト制作目的")),
            "industry": _s(row.get("業種")),
            "industry_category": _s(row.get("業種カテゴリー")),
            "area": composed_area,
            "writing_request": _s(row.get("ライティング要望")),
            "design_request": _s(row.get("デザイン要望")),
            "production_kind": production_kind,
            "ai_support": ai_support_raw,
        },
        "flags": flags,
        "store": store,
        "pages": _parse_page_slots(row),
        "existing_pages": _parse_existing_pages(row),
        "form_pages": _parse_named_url_slots(row, prefix="フォームURL", existing_suffix="既存フォーム"),
        "access_pages": _parse_named_url_slots(row, prefix="アクセスURL", existing_suffix="既存アクセス"),
        "blog_pages": _parse_named_url_slots(row, prefix="ブログURL", existing_suffix="既存ブログ"),
        "sitemap": {
            "page_name": _s(row.get("サイトマップURL (ページ名)")),
            "url": _s(row.get("サイトマップURL (URL)")) or _s(row.get("サイトマップURL")),
        },
        "privacy": {
            "page_name": _s(row.get("プライバシーポリシー (ページ名)")),
            "url": _s(row.get("プライバシーポリシー (URL)"))
            or _s(row.get("プライバシーポリシーURL")),
            "has_policy": _yes(row.get("プライバシーポリシーはありますか？")),
        },
        "reviews": review_items,
        "recruit": {
            "enabled": flags["include_recruit"],
            "production_kind": production_kind,
            "keywords": _s(row.get("その他 (リクルート > 求人キーワード)")),
            "message": _s(row.get("その他 (リクルート > 求職者に伝えたいこと)")),
        },
        "ai_blog": {
            "enabled": flags["include_ai_blog"],
            "ai_support": ai_support_raw,
        },
        "seo_pages": _parse_seo_pages(row),
        "tag_pages": _parse_tag_pages(row),
        "dynamic_pages": _parse_dynamic_pages(row),
        "blog_urls": blog_urls,
        "reference_sites": _parse_reference_sites(row),
        "focus_keywords": _parse_focus_keywords(row),
        "tag_keywords": _parse_tag_keywords(row),
        "concept_global": _s(row.get("コンセプト")),
        "top_inherit_note": _s(row.get("TOP踏襲")),
        "column_count": len(headers),
        "filled_cell_count": sum(1 for v in values if _s(v)),
    }

    from ai_agent.v2.hearing_directives import parse_page_directives
    from ai_agent.v2.site_category import attach_site_category

    wg = hearing.get("writing_guidance") or {}
    hearing["page_directives"] = parse_page_directives(
        remarks=str(wg.get("remarks") or ""),
        writing_notes=str(wg.get("writing_notes") or ""),
        pages=list(hearing.get("pages") or []),
        reference_sites=list(hearing.get("reference_sites") or []),
    )
    return attach_site_category(hearing)
