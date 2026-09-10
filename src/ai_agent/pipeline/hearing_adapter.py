"""Normalize client hearing sheets (InfoBiz, hearing-sys, salon) to canonical JSON."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from ai_agent.pipeline.linked import parse_offers

DEFAULT_COLORS = {
    "base": "#FBF7F0",
    "ink": "#2C2A26",
    "accent-1": "#2a7d4f",
    "accent-2": "#C4A574",
}

PLACEHOLDER_EXACT = {
    "",
    "なし",
    "サイト確認",
    "契約情報と一緒",
    "掲載情報(1)",
    "000-0000-0000",
    "0000000000",
    "ご契約情報と同じ",
    "-",
    "—",
    "ー",
    "未定",
    "要確認",
    "ファイル",
    "ページ名がありません",
}

PLACEHOLDER_RE = re.compile(
    r"^(契約情報|サイト確認|掲載情報|ご契約情報|おまかせ|普通|なし)$",
    re.I,
)

DUMMY_PHONE_RE = re.compile(r"^0{3}[-–]?0{4}[-–]?0{4}$")

CSV_HEADER_ALIASES: dict[str, str] = {
    "business_name": "business_name",
    "shop_name": "business_name",
    "shop": "business_name",
    "name": "business_name",
    "店名": "business_name",
    "店舗名": "business_name",
    "サロン名": "business_name",
    "会社名": "business_name",
    "契約企業名_or_屋号": "business_name",
    "ロゴ表記名": "business_name",
    "表示企業名": "business_name",
    "catchcopy": "catchcopy",
    "catch_copy": "catchcopy",
    "tagline": "catchcopy",
    "キャッチコピー": "catchcopy",
    "concept": "concept",
    "コンセプト": "concept",
    "アピール": "concept",
    "売り": "concept",
    "area": "area",
    "エリア": "area",
    "地域": "area",
    "所在地": "area",
    "address": "address",
    "住所": "address",
    "所在地住所": "address",
    "単独店舗_(名称)": "business_name",
    "単独店舗_(住所)": "address",
    "単独店舗_(電話番号)": "phone",
    "単独店舗_(始業時間)": "hours_open",
    "単独店舗_(就業時間)": "hours_close",
    "単独店舗_(定休日)": "closed",
    "station": "station",
    "最寄駅": "station",
    "phone": "phone",
    "tel": "phone",
    "電話": "phone",
    "店舗電話番号": "phone",
    "会社電話番号": "phone",
    "hours": "hours",
    "営業時間": "hours",
    "info_biz営業時間": "hours",
    "closed": "closed",
    "定休日": "closed",
    "parking": "parking",
    "駐車場": "parking",
    "reservation": "reservation",
    "予約方法": "reservation",
    "来店時の予約": "reservation",
    "payment": "payment",
    "支払い": "payment",
    "利用できるクレジットカードの種類": "payment",
    "first_visit": "first_visit",
    "初回来店": "first_visit",
    "target": "target",
    "ターゲット": "target",
    "主なお客様層": "target",
    "tone": "tone",
    "トーン": "tone",
    "ライティング要望": "tone",
    "人柄": "tone",
    "文章の柔らかさ": "tone_softness",
    "atmosphere": "atmosphere",
    "雰囲気": "atmosphere",
    "求めたい雰囲気": "atmosphere",
    "services": "services",
    "menu": "menu",
    "サービス": "services",
    "メニュー": "services",
    "施術": "services",
    "価格": "services",
    "施設": "services",
    "forbidden": "forbidden",
    "禁止表現": "forbidden",
    "ライティングngテイスト": "forbidden",
    "求めたくない雰囲気": "forbidden",
    "missing": "missing",
    "未確認項目": "missing",
    "industry": "industry",
    "業種": "industry",
    "業種カテゴリー": "industry_category",
    "詳細業種": "industry_detail",
    "業種やサービス_メイン": "services",
    "キーワード（地域＋業種）": "area",
    "キーワード_都道府県": "prefecture",
    "キーワード_市区町村": "city",
}

KNOWN_FIELDS = {
    "business_name", "catchcopy", "concept", "area", "address", "station",
    "phone", "hours", "hours_open", "hours_close", "closed", "parking",
    "reservation", "payment", "first_visit", "target", "tone", "tone_softness",
    "atmosphere", "services", "menu", "forbidden", "missing", "industry",
    "industry_category", "industry_detail", "prefecture", "city",
}


def is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if text in PLACEHOLDER_EXACT:
        return True
    if PLACEHOLDER_RE.match(text):
        return True
    if DUMMY_PHONE_RE.match(text.replace(" ", "")):
        return True
    if text.startswith("000-0000") or text.startswith("0000000"):
        return True
    return False


def clean(value: Any) -> str:
    if is_placeholder(value):
        return ""
    return str(value or "").strip()


def _as_list(value: list[str] | str) -> list[str]:
    """Split list fields without breaking Japanese thousands separators (¥8,800)."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip() and not is_placeholder(item)]
    text = str(value or "").strip()
    if not text:
        return []
    # Split on ideographic/semicolon separators, and on commas that are NOT thousands markers.
    parts = re.split(r"[、;；\n\r]+|(?<!\d),(?!\d{3})", text)
    return [part.strip() for part in parts if part.strip() and not is_placeholder(part)]


def _normalize_header(key: str) -> str:
    raw = str(key or "").replace("\ufeff", "").strip().strip('"').strip("'")
    compact = re.sub(r"[\s\-]+", "_", raw).lower()
    return CSV_HEADER_ALIASES.get(raw, CSV_HEADER_ALIASES.get(compact, compact))


def csv_matrix(text: str) -> list[list[str]]:
    raw_text = str(text or "").replace("\ufeff", "")
    if raw_text.lower().lstrip().startswith("sep="):
        first_nl = raw_text.find("\n")
        raw_text = raw_text[first_nl + 1 :] if first_nl >= 0 else ""
    sample = raw_text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    rows: list[list[str]] = []
    for raw in csv.reader(io.StringIO(raw_text), dialect=dialect):
        cells = [str(cell or "").replace("\ufeff", "") for cell in raw]
        if any(str(cell).strip() for cell in cells):
            rows.append([cell.strip() if "\n" not in cell and "\r" not in cell else cell for cell in cells])
    if rows:
        width = len(rows[0])
        aligned: list[list[str]] = [rows[0]]
        for row in rows[1:]:
            if len(row) < width:
                row = row + [""] * (width - len(row))
            aligned.append(row[:width] if len(row) > width else row)
        return aligned
    return rows


def _wide_row(matrix: list[list[str]]) -> tuple[list[str], dict[str, str]] | None:
    if len(matrix) < 2:
        return None
    headers = [str(cell or "").strip() for cell in matrix[0]]
    for row in matrix[1:]:
        raw: dict[str, str] = {}
        for index, header in enumerate(headers):
            if not header or index >= len(row):
                continue
            raw[header] = row[index]
        if any(str(value).strip() for value in raw.values()):
            return headers, raw
    return None


def _vertical_payload(matrix: list[list[str]]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for row in matrix:
        if len(row) < 2:
            continue
        key = _normalize_header(row[0])
        if key in KNOWN_FIELDS and row[1]:
            payload[key] = row[1]
    return payload


def detect_source(headers: list[str]) -> str:
    joined = " ".join(headers)
    if "ヒヤリング担当者" in joined or "単独店舗 (名称)" in joined or "ライティング要望" in joined:
        return "hearing_sys"
    if "info Bizプラン" in joined or "infoBizメールアドレス" in joined or "契約会社名" in joined:
        return "infobix"
    if "business_name" in {_normalize_header(h) for h in headers} or "店名" in joined:
        return "salon"
    return "generic"


def _first_clean(raw: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = clean(raw.get(key))
        if value:
            return value
    return ""


def _compose_address(raw: dict[str, str]) -> str:
    direct = _first_clean(raw, "単独店舗 (住所)", "住所", "address")
    if direct:
        return direct
    parts = [
        clean(raw.get("住所_都道府県") or raw.get("店舗住所（都道府県）")),
        clean(raw.get("住所_市区町村") or raw.get("店舗住所（市区町村）")),
        clean(raw.get("住所_町名") or raw.get("店舗住所（町名）")),
        clean(raw.get("住所_丁目番地") or raw.get("店舗住所（番地）")),
        clean(raw.get("住所_建物名") or raw.get("店舗住所（建物名）")),
        clean(raw.get("都道府県")),
        clean(raw.get("市区町村")),
        clean(raw.get("町名・番地")),
        clean(raw.get("建物名")),
    ]
    return "".join(part for part in parts if part)


def _compose_hours(raw: dict[str, str]) -> str:
    direct = _first_clean(raw, "hours", "営業時間", "info Biz営業時間")
    if direct and not re.fullmatch(r"\d+[〜~\-–]\d+", direct):
        return direct
    open_h = _first_clean(raw, "単独店舗 (始業時間)", "hours_open")
    close_h = _first_clean(raw, "単独店舗 (就業時間)", "hours_close")

    def _clock(token: str) -> str:
        if re.fullmatch(r"\d{1,2}", token):
            return f"{int(token):02d}:00"
        return token

    if open_h and close_h:
        return f"{_clock(open_h)}–{_clock(close_h)}"
    if direct:
        return direct
    return ""


def prepare_hearing_for_production(hearing: dict[str, Any]) -> dict[str, Any]:
    """Normalize gaps the industry way: never invent — mark missing for ground/seal."""
    out = dict(hearing or {})
    if not str(out.get("area") or "").strip():
        out["area"] = str(out.get("address") or out.get("station") or "").strip()
    missing = list(out.get("missing") or [])
    if isinstance(missing, str):
        missing = [missing] if missing.strip() else []
    labels = {
        "station": "最寄駅",
        "phone": "電話番号",
        "hours": "営業時間",
        "closed": "定休日",
        "address": "住所",
        "menu": "メニュー詳細",
    }
    for key, label in labels.items():
        value = out.get(key)
        empty = value in (None, "", [], {})
        if key == "menu" and isinstance(value, list) and not value:
            empty = True
        if empty and label not in missing:
            missing.append(label)
    out["missing"] = missing
    out["target_page"] = out.get("target_page") or "top"
    return out


def _compose_area(raw: dict[str, str]) -> str:
    area = _first_clean(raw, "area", "地域", "エリア", "キーワード（地域＋業種）")
    pref = _first_clean(raw, "prefecture", "キーワード_都道府県", "都道府県")
    city = _first_clean(raw, "city", "キーワード_市区町村", "市区町村")
    if area:
        return area
    if pref and city:
        return f"{pref}{city}"
    return pref or city


def _compose_tone(raw: dict[str, str]) -> str:
    parts = [
        _first_clean(raw, "tone", "ライティング要望", "人柄"),
        clean(raw.get("tone_softness") or raw.get("文章の柔らかさ")),
        clean(raw.get("内容の傾向")),
        clean(raw.get("文章の視点")),
    ]
    return "。".join(part for part in parts if part)


def _compose_forbidden(raw: dict[str, str]) -> list[str]:
    items = _as_list(
        "、".join(
            filter(
                None,
                [
                    raw.get("forbidden") or raw.get("禁止表現") or "",
                    raw.get("ライティングNGテイスト") or "",
                    raw.get("求めたくない雰囲気") or "",
                    raw.get("画像NGテイスト") or "",
                ],
            )
        )
    )
    return items


def _compose_concept(raw: dict[str, str]) -> str:
    parts = [
        _first_clean(raw, "concept", "コンセプト"),
        clean(raw.get("アピール")),
        clean(raw.get("売り")),
        clean(raw.get("サイト制作目的")),
        clean(raw.get("事業内容.企業理念（コンセプト） *")),
    ]
    return "。".join(part for part in parts if part)


def _compose_industry(raw: dict[str, str]) -> str:
    parts = [
        _first_clean(raw, "industry", "業種"),
        clean(raw.get("industry_category") or raw.get("業種カテゴリー")),
        clean(raw.get("industry_detail") or raw.get("詳細業種")),
        clean(raw.get("業態")),
    ]
    return " / ".join(dict.fromkeys(part for part in parts if part))


def _alias_payload(raw: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in raw.items():
        norm = _normalize_header(key)
        if norm in KNOWN_FIELDS and value and not is_placeholder(value):
            out[norm] = str(value).strip()
    return out


def _parse_services_menu(services: str) -> list[dict[str, str]]:
    """Parse menu lines. Split on item separators only — never on commas inside ¥8,800."""
    items: list[dict[str, str]] = []
    # Items are semicolon / newline separated. ASCII commas are thousands separators in JP prices.
    for chunk in re.split(r"[;；\n]+", str(services or "")):
        chunk = chunk.strip().strip("、").strip()
        if not chunk or is_placeholder(chunk):
            continue
        match = re.match(
            r"^(.+?)\s+"
            r"(\d+\s*[/／]\s*\d+\s*分|\d+\s*分)\s+"
            r"(¥[\d,]+(?:\s*[/／]\s*¥[\d,]+)*(?:\s*[/／].*)?)$",
            chunk,
        )
        if match:
            items.append(
                {
                    "name": match.group(1).strip(),
                    "duration": re.sub(r"\s+", "", match.group(2).strip()),
                    "price": match.group(3).strip(),
                    "description": "",
                }
            )
        else:
            # Soft fallback: keep the whole chunk (do not comma-split prices).
            items.append({"name": chunk, "duration": "", "price": "", "description": ""})
    return items


def canonical_hearing(
    raw: dict[str, str],
    *,
    source: str = "generic",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build canonical hearing JSON plus parse metadata."""
    aliased = _alias_payload(raw)
    ignored = sum(1 for value in raw.values() if is_placeholder(value))

    business_name = _first_clean(
        raw,
        "business_name",
        "店舗名",
        "契約企業名 or 屋号",
        "ロゴ表記名",
        "表示企業名",
        "単独店舗 (名称)",
        "契約会社名",
        "ビジネスアカウント名",
        "契約企業名",
    )
    if not business_name and source == "infobix":
        keyword = _first_clean(raw, "キーワード（地域＋業種）", "キーワード_都道府県")
        service = _first_clean(raw, "業種やサービス_メイン", "業態")
        if keyword or service:
            business_name = " / ".join(part for part in (keyword, service) if part)
    address = _compose_address(raw)
    area = _compose_area(raw)
    hours = _compose_hours(raw)
    concept = _compose_concept(raw)
    tone = _compose_tone(raw)
    atmosphere = _as_list(
        "、".join(
            filter(
                None,
                [
                    raw.get("atmosphere") or raw.get("雰囲気") or "",
                    raw.get("求めたい雰囲気") or "",
                ],
            )
        )
    )
    services_text = "、".join(
        filter(
            None,
            [
                aliased.get("services") or raw.get("業種やサービス_メイン") or "",
                raw.get("価格") or "",
                raw.get("施設") or "",
            ],
        )
    )
    menu = _parse_services_menu(services_text) if services_text else []
    forbidden = _compose_forbidden(raw)
    missing: list[str] = []
    for label, value in (
        ("スタッフ紹介", raw.get("スタッフ")),
        ("お客様の声", raw.get("Google口コミ表示")),
        ("店内写真", raw.get("提供画像有無")),
        ("メニュー詳細", services_text),
    ):
        if not clean(value) or str(value).strip() in {"なし", "無"}:
            missing.append(label)
    for item in _as_list(raw.get("missing") or raw.get("未確認項目") or aliased.get("missing") or ""):
        if item not in missing:
            missing.append(item)

    hearing: dict[str, Any] = {
        "business_name": business_name or aliased.get("business_name", ""),
        "catchcopy": _first_clean(raw, "catchcopy", "キャッチコピー") or concept.split("。")[0][:40],
        "concept": concept,
        "industry": _compose_industry(raw) or "general",
        "area": area or address,
        "address": address,
        "station": _first_clean(raw, "station", "最寄駅"),
        "phone": _first_clean(
            raw, "phone", "店舗電話番号", "単独店舗 (電話番号)", "会社電話番号", "担当者連絡先"
        ),
        "hours": hours,
        "closed": _first_clean(
            raw, "closed", "定休日", "単独店舗 (定休日)", "単独店舗 (営業日・定休日備考)"
        ),
        "parking": _first_clean(raw, "parking", "駐車場"),
        "reservation": _first_clean(raw, "reservation", "予約方法", "来店時の予約", "予約システム"),
        "payment": _first_clean(raw, "payment", "支払い", "利用できるクレジットカードの種類"),
        "first_visit": _first_clean(raw, "first_visit", "初回来店"),
        "target": _first_clean(raw, "target", "主なお客様層", "求める人物像", "お客様のニーズ"),
        "tone": tone,
        "atmosphere": atmosphere,
        "services": _as_list(services_text),
        "menu": menu,
        "offers": [],
        "forbidden": forbidden,
        "missing": missing,
        "target_page": "top",
        "colors": dict(DEFAULT_COLORS),
    }

    if not hearing["area"]:
        hearing["area"] = hearing["address"] or hearing["station"]
    hearing["offers"] = parse_offers(hearing)

    meta = {
        "source": source,
        "profile": f"{source}_v1",
        "mapped_fields": [key for key, value in hearing.items() if value and key != "colors"],
        "ignored_placeholders": ignored,
        "raw_field_count": len(raw),
    }
    meta["table"] = build_hearing_tables(hearing, raw)
    return hearing, meta


SUMMARY_FIELDS: list[tuple[str, str, str]] = [
    ("business_name", "店名", "Shop name"),
    ("industry", "業種", "Industry"),
    ("catchcopy", "キャッチコピー", "Tagline"),
    ("concept", "コンセプト", "Concept"),
    ("target", "ターゲット", "Target"),
    ("tone", "トーン / ライティング", "Tone / writing"),
    ("atmosphere", "雰囲気", "Atmosphere"),
    ("area", "エリア", "Area"),
    ("address", "住所", "Address"),
    ("station", "最寄駅", "Station"),
    ("phone", "電話", "Phone"),
    ("hours", "営業時間", "Hours"),
    ("closed", "定休日", "Closed days"),
    ("parking", "駐車場", "Parking"),
    ("reservation", "予約", "Booking"),
    ("payment", "支払い", "Payment"),
    ("first_visit", "初回来店", "First visit"),
    ("services", "サービス", "Services"),
    ("forbidden", "禁止表現", "Forbidden"),
    ("missing", "未確認", "Still needed"),
]


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(parts)
    return str(value).strip()


def build_summary_rows(hearing: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for key, label_ja, label_en in SUMMARY_FIELDS:
        text = _format_cell(hearing.get(key))
        if not text:
            continue
        rows.append(
            {
                "key": key,
                "label_ja": label_ja,
                "label_en": label_en,
                "value": text,
            }
        )
        seen.add(key)
    for key, value in hearing.items():
        if key in seen or key in {"colors", "menu", "target_page"}:
            continue
        text = _format_cell(value)
        if not text:
            continue
        rows.append(
            {
                "key": str(key),
                "label_ja": str(key),
                "label_en": str(key),
                "value": text,
            }
        )
    return rows


def build_raw_rows(raw: dict[str, str], *, limit: int = 250) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for header, value in raw.items():
        if is_placeholder(value):
            continue
        text = str(value or "").strip()
        if not text:
            continue
        rows.append({"header": header, "value": text[:1000]})
        if len(rows) >= limit:
            break
    return rows


def build_hearing_tables(hearing: dict[str, Any], raw: dict[str, str] | None = None) -> dict[str, Any]:
    menu = hearing.get("menu") or []
    services = hearing.get("services") or []
    raw_rows = build_raw_rows(raw or {})
    summary = build_summary_rows(hearing)
    return {
        "summary": summary,
        "raw": raw_rows,
        "menu_count": len(menu) if isinstance(menu, list) else 0,
        "service_count": len(services) if isinstance(services, list) else 0,
        "default_tab": (
            "menu"
            if isinstance(menu, list) and len(menu) > 0
            else ("sheet" if len(raw_rows) > 12 else "summary")
        ),
    }


def parse_hearing_csv(raw: str) -> tuple[dict[str, Any], dict[str, Any]]:
    text = str(raw or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("CSV has no data row")
    matrix = csv_matrix(text)
    if not matrix:
        raise ValueError("CSV has no data row")

    vertical_hits = sum(1 for row in matrix if row and _normalize_header(row[0]) in KNOWN_FIELDS)
    wide = _wide_row(matrix)
    source = detect_source(matrix[0]) if matrix else "generic"

    if vertical_hits >= 2 and max(len(row) for row in matrix) <= 4:
        payload = _vertical_payload(matrix)
        hearing, meta = canonical_hearing(payload, source="vertical")
        meta["source"] = "vertical"
        meta["table"] = build_hearing_tables(hearing, payload)
        return hearing, meta

    if not wide:
        raise ValueError("CSV has no data row")
    headers, raw_row = wide
    source = detect_source(headers)
    hearing, meta = canonical_hearing(raw_row, source=source)
    return hearing, meta
