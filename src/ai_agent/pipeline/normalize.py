"""Normalize protected values without changing semantic meaning."""

from __future__ import annotations

import re

from ai_agent.pipeline.facts import YEN_DISPLAY_RE, YEN_JP_RE, format_yen

PHONE_CANDIDATE_RE = re.compile(
    r"(?<!\d)(0\d{1,4}[-–−.\s()]*\d{1,4}[-–−.\s()]*\d{3,4})(?!\d)"
)
WALK_RE = re.compile(r"徒歩\s*(\d+)\s*分")
STATION_NAME_RE = re.compile(r"([一-龯ぁ-んァ-ンA-Za-z0-9]{2,12}駅)")
TIME_RE = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"[\s\u3000]+", " ", str(text or "")).strip()


def normalize_phone(text: str) -> str:
    """Digits-only phone. Empty if not a plausible JP number."""
    digits = re.sub(r"\D", "", str(text or ""))
    if len(digits) < 10 or len(digits) > 11:
        return ""
    if not digits.startswith("0"):
        return ""
    return digits


def normalize_price(text: str) -> str:
    """Canonical yen digits (8800). Empty if not a full amount."""
    raw = str(text or "")
    for match in YEN_DISPLAY_RE.finditer(raw):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4:
            return digits
    for match in YEN_JP_RE.finditer(raw):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4:
            return digits
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 4:
        return digits
    return ""


def normalize_station(text: str) -> str:
    """Station name fragment ending in 駅, if present."""
    text = normalize_whitespace(text)
    match = STATION_NAME_RE.search(text)
    return match.group(1) if match else text


def normalize_time(text: str) -> str:
    """HH:MM 24h. Empty if not a clock time."""
    match = TIME_RE.search(str(text or ""))
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def walking_minutes(text: str) -> int | None:
    match = WALK_RE.search(str(text or ""))
    if not match:
        return None
    return int(match.group(1))


def extract_phones(text: str) -> list[str]:
    """Each phone-like span, normalized independently (never concatenate the page)."""
    found: list[str] = []
    for match in PHONE_CANDIDATE_RE.finditer(str(text or "")):
        norm = normalize_phone(match.group(1))
        if norm and norm not in found:
            found.append(norm)
    return found


def extract_prices(text: str) -> list[str]:
    out: list[str] = []
    for match in YEN_DISPLAY_RE.finditer(str(text or "")):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4 and digits not in out:
            out.append(digits)
    for match in YEN_JP_RE.finditer(str(text or "")):
        digits = re.sub(r"\D", "", match.group(1) or "")
        if len(digits) >= 4 and digits not in out:
            out.append(digits)
    return out


def format_price_digits(digits: str) -> str:
    return format_yen(digits)
