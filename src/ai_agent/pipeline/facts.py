"""Hearing sheet is the single source of truth for protected facts."""

from __future__ import annotations

import json
import re
from typing import Any

# Full yen amounts only — never match the "¥8" prefix of "¥8,800".
YEN_DISPLAY_RE = re.compile(
    r"[¥￥]\s*(\d{1,3}(?:,\d{3})+|\d{4,})(?:\s*円)?"
)
YEN_JP_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,})\s*円")
PHONE_RE = re.compile(r"0\d{1,4}[-–−(]?\d{1,4}[-–−)]?\d{3,4}")
# Broken model/parser output: ¥8 then 800 on the next fragment.
YEN_SPLIT_RE = re.compile(
    r"[¥￥]\s*(\d{1,3})\s*[\n/／,、\s]+\s*(\d{3})(?!\d)"
)
PARA_YEN_TAIL = re.compile(r"[¥￥]\s*(\d{1,3})\s*$")
PARA_YEN_HEAD = re.compile(r"^(\d{3})(?!\d)")
TBD = "要ヒアリング"
_STATION_NAME_RE = re.compile(r"([一-龯ぁ-んァ-ンA-Za-z0-9]{2,12}駅)")
_WALK_NUM_RE = re.compile(r"徒歩\s*([0-9０-９]+)\s*分")
_FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
# TBD occupying the station slot. Do not require a tight "要ヒアリングから徒歩" spelling.
TBD_WALK_RE = re.compile(
    r"要ヒアリング(?:駅)?"
    r"(?:\s*[の、,]*\s*)?"
    r"(?:から|より)?"
    r"\s*徒歩(?:\s*[0-9０-９]+\s*分)?"
)
ORPHAN_WALK_RE = re.compile(
    r"(^|[。！？\n「『（\(])(\s*)(?:から|より)徒歩\s*[0-9０-９]+\s*分"
)

PROTECTED_KEYS = (
    "business_name",
    "address",
    "station",
    "phone",
    "hours",
    "closed",
    "parking",
    "reservation",
    "payment",
    "first_visit",
)

PROSE_FIELDS = ("title", "heading", "lead", "cta")


def hearing_blob(hearing: dict[str, Any]) -> str:
    return json.dumps(hearing, ensure_ascii=False, default=str)


def copy_blob(copy: dict[str, Any]) -> str:
    parts = [str(copy.get(k) or "") for k in PROSE_FIELDS]
    paras = copy.get("body_paragraphs") or []
    if isinstance(paras, list):
        parts.extend(str(p) for p in paras)
    else:
        parts.append(str(paras))
    parts.append(str(copy.get("notes") or ""))
    return "\n".join(parts)


def yen_digits(text: str) -> set[str]:
    """Canonical digit strings for prices (8800 from ¥8,800)."""
    out: set[str] = set()
    for match in YEN_DISPLAY_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4:
            out.add(digits)
    for match in YEN_JP_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4:
            out.add(digits)
    return out


def yen_displays(text: str) -> list[str]:
    found: list[str] = []
    for match in YEN_DISPLAY_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4:
            found.append(format_yen(digits))
    for match in YEN_JP_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4:
            disp = format_yen(digits)
            if disp not in found:
                found.append(disp)
    return found


def format_yen(digits: str) -> str:
    digits = re.sub(r"\D", "", digits)
    if not digits:
        return ""
    grouped = f"{int(digits):,}"
    return f"¥{grouped}"


def join_split_yen(text: str, allowed_digits: set[str]) -> str:
    """Repair ¥8 / 800 → ¥8,800 when the combined amount is in source data."""

    def repl(match: re.Match[str]) -> str:
        combined = match.group(1) + match.group(2)
        if combined in allowed_digits:
            return format_yen(combined)
        return match.group(0)

    return YEN_SPLIT_RE.sub(repl, text or "")


def hearing_yen_digits(hearing: dict[str, Any]) -> set[str]:
    return yen_digits(hearing_blob(hearing))


def hearing_prices(hearing: dict[str, Any]) -> list[str]:
    prices: list[str] = []
    for item in hearing.get("menu") or []:
        if isinstance(item, dict):
            prices.extend(yen_displays(str(item.get("price") or "")))
        else:
            prices.extend(yen_displays(str(item)))
    prices.extend(yen_displays(str(hearing.get("services") or "")))
    # Preserve order, unique
    seen: set[str] = set()
    out: list[str] = []
    for p in prices:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def protected_strings(hearing: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in PROTECTED_KEYS:
        val = str(hearing.get(key) or "").strip()
        if val:
            out[key] = val
    for i, item in enumerate(hearing.get("menu") or []):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            price = str(item.get("price") or "").strip()
            if name:
                out[f"menu.{i}.name"] = name
            if price:
                out[f"menu.{i}.price"] = price
    return out


def span_supported_by_hearing(span: str, hearing: dict[str, Any]) -> bool:
    text = str(span or "").strip()
    if not text or text == TBD:
        return False
    blob = hearing_blob(hearing)
    if text in blob:
        return True
    for val in protected_strings(hearing).values():
        if text in val or val in text:
            return True
    allowed = hearing_yen_digits(hearing)
    for digits in yen_digits(text):
        if digits in allowed:
            return True
    for phone in PHONE_RE.findall(text):
        if phone in blob:
            return True
    return False


def station_short_name(station: str) -> str:
    match = _STATION_NAME_RE.search(str(station or ""))
    return match.group(1) if match else ""


def access_restoration_phrase(hearing: dict[str, Any]) -> str:
    """Natural access phrase from source, e.g. 東急田園都市線 桜新町駅から徒歩4分."""
    station = str(hearing.get("station") or "").strip()
    name_match = _STATION_NAME_RE.search(station)
    if not name_match:
        return station
    name = name_match.group(1)
    prefix = station[: name_match.start()].strip()
    minutes = None
    walk = _WALK_NUM_RE.search(station)
    if walk:
        minutes = int(walk.group(1).translate(_FW_DIGITS))
    if minutes is None:
        return station
    if prefix:
        return f"{prefix} {name}から徒歩{minutes}分"
    return f"{name}から徒歩{minutes}分"


def restore_station_walk(text: str, hearing: dict[str, Any]) -> str:
    """Never delete 要ヒアリング in front of 徒歩 — restore the source station instead."""
    station = str(hearing.get("station") or "").strip()
    if not station:
        return str(text or "")
    name = station_short_name(station)
    phrase = access_restoration_phrase(hearing)
    out = str(text or "")
    if TBD_WALK_RE.search(out):
        out = TBD_WALK_RE.sub(phrase, out)
    if name and name not in out:
        out = ORPHAN_WALK_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{phrase}", out)
        stripped = out.lstrip()
        if stripped.startswith("から徒歩") or stripped.startswith("より徒歩"):
            lead_ws = out[: len(out) - len(stripped)]
            idx = stripped.find("分")
            rest = stripped[idx + 1 :] if idx >= 0 else ""
            out = f"{lead_ws}{phrase}{rest}"
    return out


def restore_protected_copy(copy: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Deterministically undo known-fact damage (split yen, TBD-over-station, etc.)."""
    from ai_agent.pipeline.linked import restore_linked_tbd

    allowed = hearing_yen_digits(hearing)
    out = dict(copy)
    paras = list(out.get("body_paragraphs") or [])
    if not isinstance(paras, list):
        paras = [str(paras)]

    def fix_field(text: str) -> str:
        text = join_split_yen(str(text or ""), allowed)
        text = restore_station_walk(text, hearing)
        text, _repairs = restore_linked_tbd(text, hearing)
        return text

    for key in PROSE_FIELDS:
        out[key] = fix_field(str(out.get(key) or ""))
    paras = [fix_field(str(p)) for p in paras]
    # Join ¥8 | 800 split across adjacent paragraphs.
    merged: list[str] = []
    i = 0
    while i < len(paras):
        cur = paras[i]
        tail = PARA_YEN_TAIL.search(cur)
        if tail and i + 1 < len(paras):
            head = PARA_YEN_HEAD.search(paras[i + 1])
            if head:
                combined = tail.group(1) + head.group(1)
                if combined in allowed:
                    cur = PARA_YEN_TAIL.sub(format_yen(combined), cur, count=1)
                    paras[i + 1] = PARA_YEN_HEAD.sub("", paras[i + 1], count=1).lstrip(" /／、")
        merged.append(cur)
        i += 1
    out["body_paragraphs"] = merged
    out["notes"] = str(out.get("notes") or "")
    return out


def strip_tbd_from_prose(copy: dict[str, Any], hearing: dict[str, Any] | None = None) -> dict[str, Any]:
    """要ヒアリング is not allowed in publishable prose fields.

    Station placeholders are restored from source before any deletion, so
    `要ヒアリングから徒歩4分` never becomes `から徒歩4分`.
    """
    out = dict(copy)

    def clean(text: str) -> str:
        text = str(text or "")
        if hearing:
            text = restore_station_walk(text, hearing)
        text = text.replace(TBD, "")
        text = re.sub(r"\s{2,}", " ", text).strip(" \t・、:")
        return text.strip()

    for key in PROSE_FIELDS:
        out[key] = clean(str(out.get(key) or ""))
    paras = out.get("body_paragraphs") or []
    if isinstance(paras, list):
        out["body_paragraphs"] = [clean(str(p)) for p in paras]
    return out


def tbd_violations(copy: dict[str, Any], hearing: dict[str, Any]) -> list[dict[str, str]]:
    """source has value + output says 要ヒアリング → failure with exact field."""
    issues: list[dict[str, str]] = []
    blob = copy_blob(copy)
    protected = protected_strings(hearing)

    def check_field(field: str, text: str) -> None:
        if TBD not in text:
            return
        for key, source in protected.items():
            token = source
            digits = yen_digits(source)
            present = token in blob or bool(digits and digits.issubset(yen_digits(blob)))
            if not present:
                issues.append(
                    {
                        "field": field,
                        "type": "SOURCE_MISMATCH",
                        "original": source,
                        "generated": TBD,
                        "source_key": key,
                    }
                )

    for key in PROSE_FIELDS:
        check_field(key, str(copy.get(key) or ""))
    paras = copy.get("body_paragraphs") or []
    if isinstance(paras, list):
        for i, para in enumerate(paras):
            check_field(f"body_{i + 1}", str(para))
    elif TBD in str(paras):
        check_field("body_paragraphs", str(paras))
    return issues
