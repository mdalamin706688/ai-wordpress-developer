"""Score generated Japanese copy against a canonical hearing sheet."""

from __future__ import annotations

import re
from typing import Any

from ai_agent.pipeline.grounding import YEN_RE, _phones

FORBIDDEN_DEFAULT = ["治る", "必ず", "医療", "医師監修", "今すぐ", "完治", "必ず改善"]

# Client-facing lab rubric: always 8 comparable facts (same keys every run).
LAB_FACT_KEYS = (
    "shop",
    "station",
    "hours",
    "closed",
    "phone",
    "aromatherapy",
    "headspa",
    "price",
)


def _joined(copy: dict[str, Any]) -> str:
    parts = [
        copy.get("title") or "",
        copy.get("heading") or "",
        copy.get("lead") or "",
        copy.get("cta") or "",
        *list(copy.get("body_paragraphs") or []),
    ]
    return "\n".join(str(part) for part in parts if str(part).strip())


def _hearing_tokens(hearing: dict[str, Any]) -> dict[str, str]:
    import json

    blob = json.dumps(hearing, ensure_ascii=False)
    tokens: dict[str, str] = {}
    name = str(hearing.get("business_name") or "").strip()
    if len(name) >= 2:
        tokens["shop"] = name[: min(8, len(name))]
    for key in ("station", "area", "address", "phone", "hours", "closed"):
        value = str(hearing.get(key) or "").strip()
        if value and len(value) >= 2:
            tokens[key] = value[: min(12, len(value))]
    for item in hearing.get("menu") or []:
        if isinstance(item, dict):
            price = str(item.get("price") or "")
            match = YEN_RE.search(price)
            if match:
                digits = re.sub(r"\D", "", next(g for g in match.groups() if g) or "")
                if digits:
                    tokens.setdefault("price", digits)
            name = str(item.get("name") or "").strip()
            if name:
                tokens[f"menu_{name[:6]}"] = name[:8]
    for service in hearing.get("services") or []:
        text = str(service).strip()
        if text:
            tokens[f"service_{text[:6]}"] = text[:10]
    if "10:00" in blob or "10：" in blob:
        tokens.setdefault("hours", "10")
    phones = _phones(blob)
    if phones:
        tokens["phone_digits"] = next(iter(phones))
    return tokens


def score_copy(copy: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    text = _joined(copy)
    tokens = _hearing_tokens(hearing)
    facts = {key: token in text for key, token in tokens.items()}
    forbidden = list(dict.fromkeys((hearing.get("forbidden") or []) + FORBIDDEN_DEFAULT))
    forbidden_hits = [word for word in forbidden if word and str(word) in text]
    tbd_count = text.count("要ヒアリング")
    paras = copy.get("body_paragraphs") or []
    return {
        "facts_hit": sum(facts.values()),
        "facts_total": len(tokens),
        "facts": facts,
        "paragraphs": len(paras) if isinstance(paras, list) else 0,
        "chars": len(text),
        "forbidden_hits": forbidden_hits,
        "tbd_markers": tbd_count,
        "has_heading": bool(copy.get("heading")),
        "has_cta": bool(copy.get("cta")),
        "heading": copy.get("heading") or "",
        "lead": (copy.get("lead") or "")[:200],
        "cta": copy.get("cta") or "",
    }


def build_lab_fact_tokens(hearing: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Facts present in this hearing only (no salon-only tokens unless hearing has them)."""
    name = str(hearing.get("business_name") or "").strip()
    station = str(hearing.get("station") or "").strip()
    hours = str(hearing.get("hours") or "").strip()
    closed = str(hearing.get("closed") or "").strip()
    phone = str(hearing.get("phone") or "").strip()
    address = str(hearing.get("address") or "").strip()
    area = str(hearing.get("area") or "").strip()

    shop_tok = name[: min(8, len(name))] if len(name) >= 2 else ""
    station_tok = ""
    for part in re.split(r"[\s　/｜|]", station):
        part = part.strip()
        if len(part) >= 2:
            station_tok = part.replace("駅", "")[:6] or part[:6]
            break
    if not station_tok and len(station) >= 2:
        station_tok = station[:6]

    hours_tok = ""
    hm = re.search(r"(\d{1,2}:\d{2})", hours)
    if hm:
        hours_tok = hm.group(1)
    elif hours and not re.fullmatch(r"\d+[〜~\-–]\d+", hours):
        hours_tok = hours[:8]

    closed_tok = closed[:4] if len(closed) >= 2 else ""
    phone_tok = phone if phone and not phone.startswith("000") else ""
    address_tok = address[:10] if len(address) >= 4 else ""
    area_tok = area[:4] if len(area) >= 2 else ""

    blob = " ".join(
        [
            str(hearing.get("concept") or ""),
            str(hearing.get("catchcopy") or ""),
            " ".join(str(s) for s in (hearing.get("services") or [])),
            " ".join(
                str(m.get("name") or "")
                for m in (hearing.get("menu") or [])
                if isinstance(m, dict)
            ),
        ]
    )
    aroma_tok = "アロマ" if "アロマ" in blob else ""
    head_tok = "ヘッドスパ" if ("ヘッドスパ" in blob or "ヘッド" in blob) else ""

    price_tok = ""
    for item in hearing.get("menu") or []:
        if not isinstance(item, dict):
            continue
        match = YEN_RE.search(str(item.get("price") or ""))
        if match:
            raw = next(g for g in match.groups() if g) or ""
            price_tok = raw.strip()
            break

    candidates = [
        ("shop", "店名", shop_tok),
        ("area", "エリア", area_tok),
        ("address", "住所", address_tok),
        ("station", "最寄駅", station_tok),
        ("hours", "営業時間", hours_tok),
        ("closed", "定休日", closed_tok),
        ("phone", "電話", phone_tok),
        ("aromatherapy", "アロマ", aroma_tok),
        ("headspa", "ヘッドスパ", head_tok),
        ("price", "価格", price_tok),
    ]
    # Only score facts the hearing actually provides — empty tokens are N/A, not failures.
    return [(key, label, token) for key, label, token in candidates if token]


def score_lab_copy(copy: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Score only known hearing facts. Missing hearing fields do not lower the %."""
    text = _joined(copy)
    fact_defs = build_lab_fact_tokens(hearing)
    facts_detail: dict[str, Any] = {}
    for key, label_ja, token in fact_defs:
        hit = token in text
        # Allow shorter shop/area match if truncated token is awkward
        if not hit and key in {"shop", "area", "address"} and len(token) >= 2:
            hit = token[:2] in text
        facts_detail[key] = {
            "label_ja": label_ja,
            "token": token,
            "hit": hit,
            "applicable": True,
        }
    facts = {key: item["hit"] for key, item in facts_detail.items()}
    forbidden = list(dict.fromkeys((hearing.get("forbidden") or []) + FORBIDDEN_DEFAULT))
    forbidden_hits = [word for word in forbidden if word and str(word) in text]
    paras = copy.get("body_paragraphs") or []
    para_n = len(paras) if isinstance(paras, list) else 0
    chars = len(text)
    has_heading = bool(str(copy.get("heading") or "").strip())
    has_lead = bool(str(copy.get("lead") or "").strip())
    has_cta = bool(str(copy.get("cta") or "").strip())
    complete = para_n >= 6 and has_heading and has_lead and has_cta and chars >= 200
    hit = sum(1 for v in facts.values() if v)
    total = len(facts_detail)
    # No applicable facts → treat as N/A 100% only if structure complete and no forbidden
    if total == 0:
        pct = 100 if complete and not forbidden_hits else 0
        hit, total = (1, 1) if pct == 100 else (0, 1)
    else:
        pct = round(100 * hit / total)
    missing = hearing.get("missing") or []
    if isinstance(missing, str):
        missing = [missing] if missing.strip() else []
    grounded_missing = bool(missing) and ("要ヒアリング" in text)
    return {
        "facts_hit": hit,
        "facts_total": total,
        "facts_pct": pct,
        "facts": facts,
        "facts_detail": facts_detail,
        "paragraphs": para_n,
        "chars": chars,
        "forbidden_hits": forbidden_hits,
        "tbd_markers": text.count("要ヒアリング"),
        "grounded_missing": grounded_missing,
        "has_heading": has_heading,
        "has_lead": has_lead,
        "has_cta": has_cta,
        "complete": complete,
        "heading": copy.get("heading") or "",
        "lead": (copy.get("lead") or "")[:200],
        "cta": copy.get("cta") or "",
        "rubric": "known_hearing_facts_only",
    }
