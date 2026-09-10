"""Hearing-only fact pack and a deterministic anti-hallucination pass."""

from __future__ import annotations

import re
from typing import Any

from ai_agent.pipeline.facts import (
    PHONE_RE,
    YEN_DISPLAY_RE,
    YEN_JP_RE,
    hearing_blob,
    span_supported_by_hearing,
    yen_digits,
)

YEN_RE = YEN_DISPLAY_RE

STATION_RE = re.compile(r"[一-龯ぁ-んァ-ンA-Za-z0-9]{2,12}駅")
GENERIC_STATION_WORDS = frozenset({"最寄駅", "最寄り駅", "駅前", "各駅", "近隣駅"})
HYPE_RE = re.compile(
    r"必ず改善|必ず治|絶対に|完治|治癒|治ります|医師監修|医療行為|治療効果|今すぐ予約|日本一|No\.?\s*1|必ず痩せる"
)
COUNT_RE = re.compile(r"\d{1,3}名")
FOUNDING_RE = re.compile(r"(?:創業|開業|設立)\s*\d{1,4}年")
TESTIMONIAL_RE = re.compile(r"お客様の声|口コミで|レビューで|満足度\s*\d|高評価を")

MISSING_HINTS = {
    "スタッフ紹介": re.compile(r"スタッフの[名前紹介]|在籍スタイリスト|担当セラピストは"),
    "お客様の声": TESTIMONIAL_RE,
    "店内写真": re.compile(r"写真はこちら|ギャラリーをご覧"),
}

# (pattern, required source token). If the token is absent from the hearing, strip the claim.
INFERENCE_RULES: list[tuple[str, str]] = [
    (r"完全個室(?:の[^。、]{0,16})?", "個室"),
    (r"個室でのサービスを中心に[、。]?", "個室"),
    (r"個室での", "個室"),
    (r"個室を", "個室"),
    (r"個室", "個室"),
    (r"心地よい香りに包まれながら[、]?", "香り"),
    (r"心地よい香りを漂わせた空間[、。]?", "香り"),
    (r"アロマの香りが漂[いいう][^。]{0,10}", "香り"),
    (r"香り(?:の(?:ある|良い|よい))?空間", "香り"),
    (r"全身を心地よくほぐす", "ほぐす"),
    (r"全身をほぐす", "ほぐす"),
    (r"足元をすっきり整える", "すっきり"),
    (r"ご自身のニーズに合ったサービスをご案内(?:します|いたします)?", "ご案内"),
    (r"ニーズに合ったサービスをご案内", "ご案内"),
    (r"お体の状態やご希望を事前にお伺い(?:いたします|します)", "お体の状態"),
    (r"最適なメニューをご提案(?:いたします|します)?", "ご提案"),
]


def strip_unsupported_inferences(text: str, hearing: dict[str, Any]) -> str:
    """Remove atmospheric/operational claims the hearing sheet does not support."""
    blob = hearing_blob(hearing)
    out = str(text or "")
    for pattern, token in INFERENCE_RULES:
        if token and token in blob:
            continue
        out = re.sub(pattern, "", out)
    return re.sub(r"\s{2,}", " ", out).strip()

__all__ = [
    "YEN_RE",
    "_phones",
    "fact_pack",
    "ground_copy",
    "hearing_blob",
    "span_supported_by_hearing",
]


def fact_pack(hearing: dict[str, Any]) -> str:
    """Compact allowed-facts list injected into writer/reviewer prompts."""
    menu = hearing.get("menu") or []
    menu_lines = []
    if isinstance(menu, list):
        for item in menu:
            if isinstance(item, dict):
                menu_lines.append(
                    " / ".join(
                        str(item.get(key) or "").strip()
                        for key in ("name", "description", "duration", "price")
                        if str(item.get(key) or "").strip()
                    )
                )
            elif str(item).strip():
                menu_lines.append(str(item).strip())
    services = hearing.get("services") or []
    if isinstance(services, str):
        services = [services]
    missing = hearing.get("missing") or []
    if isinstance(missing, str):
        missing = [missing]
    forbidden = hearing.get("forbidden") or []
    if isinstance(forbidden, str):
        forbidden = [forbidden]

    def line(label: str, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return f"{label}: {text}"

    known: list[str] = []
    for label, value in (
        ("店名", hearing.get("business_name")),
        ("キャッチ", hearing.get("catchcopy")),
        ("コンセプト", hearing.get("concept")),
        ("エリア", hearing.get("area")),
        ("住所", hearing.get("address")),
        ("最寄駅", hearing.get("station")),
        ("電話", hearing.get("phone")),
        ("営業時間", hearing.get("hours")),
        ("定休", hearing.get("closed")),
        ("駐車場", hearing.get("parking")),
        ("予約", hearing.get("reservation")),
        ("支払い", hearing.get("payment")),
        ("初回", hearing.get("first_visit")),
        ("対象", hearing.get("target")),
        ("トーン", hearing.get("tone")),
        (
            "雰囲気",
            ", ".join(
                str(x) for x in (hearing.get("atmosphere") or []) if str(x).strip()
            ),
        ),
        ("メニュー", "；".join(menu_lines)),
        (
            "サービス名",
            ", ".join(str(x) for x in services if str(x).strip()),
        ),
    ):
        row = line(label, value)
        if row:
            known.append(row)

    known.append(
        "書いてはいけない: "
        + (
            ", ".join(str(x) for x in forbidden if str(x).strip())
            or "（なし）"
        )
    )
    known.append(
        "未確認（本文に書かない）: "
        + (
            ", ".join(str(x) for x in missing if str(x).strip())
            or "（なし）"
        )
    )
    known.append(
        "ルール: 上に無い項目は本文へ書かない。"
        "許可された料金・駅・電話は原文のまま使う。"
        "最寄駅は省略せず、ヒアリングの駅名＋徒歩分を使う。"
        "「から徒歩N分」だけで文を始めない。文頭を「は」だけで始めない。"
        "一般描写を設備・資格・保証・効果に変換しない（プライベート空間≠完全個室）。"
        "未記載は省略する。発明しない。"
        "ヒアリングに無い個室・香り・効果効能・案内約束を作らない。"
        "本文に「要ヒアリング」を埋め込まない。"
    )
    return "\n".join(known)


def _phones(text: str) -> set[str]:
    return {re.sub(r"\D", "", m) for m in PHONE_RE.findall(text or "") if re.sub(r"\D", "", m)}


def _allowed_geo_blob(hearing: dict[str, Any]) -> str:
    parts = [
        hearing.get("station"),
        hearing.get("address"),
        hearing.get("area"),
        hearing.get("business_name"),
    ]
    return " ".join(str(p or "") for p in parts)


def _strip_unsupported(text: str, hearing: dict[str, Any]) -> str:
    allowed = hearing_blob(hearing)
    allowed_yen = yen_digits(allowed)
    allowed_phones = _phones(allowed)
    geo = _allowed_geo_blob(hearing)
    missing = {str(x) for x in (hearing.get("missing") or [])}

    def replace_yen(match: re.Match[str]) -> str:
        raw = next((g for g in match.groups() if g), "")
        digits = re.sub(r"\D", "", raw)
        if digits and digits in allowed_yen:
            return match.group(0)
        return ""  # drop invented prices — do not inject 要ヒアリング

    text = YEN_DISPLAY_RE.sub(replace_yen, text or "")
    text = YEN_JP_RE.sub(replace_yen, text)

    def replace_phone(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if digits in allowed_phones:
            return match.group(0)
        return ""

    text = PHONE_RE.sub(replace_phone, text)

    for station in STATION_RE.findall(text):
        if station in GENERIC_STATION_WORDS:
            continue
        if station not in geo and station not in allowed:
            text = text.replace(station, "")

    text = HYPE_RE.sub("", text)
    for match in COUNT_RE.finditer(text):
        if match.group(0) not in allowed:
            text = text.replace(match.group(0), "")
    for match in FOUNDING_RE.finditer(text):
        if match.group(0) not in allowed:
            text = text.replace(match.group(0), "")
    for label, pattern in MISSING_HINTS.items():
        if any(label in item for item in missing):
            text = pattern.sub("", text)
    text = strip_unsupported_inferences(text, hearing)
    from ai_agent.pipeline.claims import strip_high_risk_claims

    text = strip_high_risk_claims(text, hearing)
    return re.sub(r"\s{2,}", " ", text).strip()


def ground_copy(copy: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Remove prices, phones, stations, and hype that are not in the hearing."""
    out = dict(copy)
    for key in ("title", "heading", "lead", "cta", "notes"):
        out[key] = _strip_unsupported(str(out.get(key) or ""), hearing)
    paras = out.get("body_paragraphs") or []
    if isinstance(paras, str):
        paras = [paras]
    cleaned = [_strip_unsupported(str(p), hearing).strip() for p in paras if str(p).strip()]
    out["body_paragraphs"] = cleaned[:6] if cleaned else [""]
    if not str(out.get("cta") or "").strip():
        out["cta"] = "ご予約はこちら"
    return out
