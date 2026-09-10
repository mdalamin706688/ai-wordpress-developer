"""Linked hearing facts: service+duration+price, station+walk, name+address."""

from __future__ import annotations

import re
from typing import Any

from ai_agent.pipeline.normalize import (
    extract_phones,
    extract_prices,
    normalize_phone,
    normalize_station,
    walking_minutes,
)

GENERIC_STATION_WORDS = frozenset({"最寄駅", "最寄り駅", "駅前", "各駅", "近隣駅"})
DURATION_RE = re.compile(r"(\d+)\s*分")


def parse_offers(hearing: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured offers from canonical menu rows."""
    cached = hearing.get("offers")
    if isinstance(cached, list) and cached and isinstance(cached[0], dict) and "price" in cached[0]:
        return [dict(item) for item in cached]
    offers: list[dict[str, Any]] = []
    for item in hearing.get("menu") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        duration = str(item.get("duration") or "")
        price = str(item.get("price") or "")
        mins = [int(x) for x in re.findall(r"\d+", duration)]
        prices = [int(p) for p in extract_prices(price)]
        if name and mins and prices and len(mins) == len(prices):
            for minute, yen in zip(mins, prices, strict=False):
                offers.append(
                    {
                        "service": name,
                        "duration_minutes": minute,
                        "price": yen,
                    }
                )
        elif name and len(prices) == 1:
            offers.append(
                {
                    "service": name,
                    "duration_minutes": mins[0] if len(mins) == 1 else None,
                    "price": prices[0],
                }
            )
    return offers


def station_access(hearing: dict[str, Any]) -> dict[str, Any]:
    station = str(hearing.get("station") or "")
    return {
        "station": normalize_station(station),
        "walking_minutes": walking_minutes(station),
        "address": str(hearing.get("address") or "").strip(),
        "business_name": str(hearing.get("business_name") or "").strip(),
        "phone": normalize_phone(str(hearing.get("phone") or "")),
        "hours": str(hearing.get("hours") or "").strip(),
    }


def _price_int(span: str) -> int | None:
    digits = re.sub(r"\D", "", span)
    if len(digits) < 4:
        return None
    return int(digits)


def _service_pairs(text: str, service: str) -> list[tuple[int | None, int]]:
    """Duration/price pairs attached to one service mention — never a bag of all numbers."""
    escaped = re.escape(service)
    pairs: list[tuple[int | None, int]] = []
    slash = re.search(
        escaped
        + r"\s*[:：は]?\s*(\d+(?:\s*[/／]\s*\d+)+)\s*分\s*"
        + r"((?:[¥￥]\s*\d{1,3}(?:,\d{3})+(?:\s*[/／]\s*[¥￥]\s*\d{1,3}(?:,\d{3})+)+))",
        text,
    )
    if slash:
        mins = [int(x) for x in re.findall(r"\d+", slash.group(1))]
        prices = [int(p) for p in extract_prices(slash.group(2))]
        if len(mins) == len(prices):
            return list(zip(mins, prices, strict=True))
    seq = re.compile(
        escaped
        + r".{0,16}?(\d+)\s*分.{0,16}?"
        + r"([¥￥]\s*\d{1,3}(?:,\d{3})+|[¥￥]\s*\d{4,}|(?:\d{1,3}(?:,\d{3})+|\d{4,})\s*円)"
    )
    for match in seq.finditer(text):
        yen = _price_int(match.group(2))
        if yen is not None:
            pairs.append((int(match.group(1)), yen))
    if pairs:
        return pairs
    loose = re.compile(
        escaped
        + r".{0,20}?"
        + r"([¥￥]\s*\d{1,3}(?:,\d{3})+|[¥￥]\s*\d{4,})"
    )
    for match in loose.finditer(text):
        if "分" in match.group(0):
            continue
        yen = _price_int(match.group(1))
        if yen is not None:
            pairs.append((None, yen))
    return pairs


def linked_fact_issues(copy_text: str, hearing: dict[str, Any]) -> list[dict[str, str]]:
    """Fail when generated text pairs facts that the hearing sheet does not pair."""
    text = str(copy_text or "")
    issues: list[dict[str, str]] = []
    offers = parse_offers(hearing)
    access = station_access(hearing)

    by_service_dur: dict[tuple[str, int], int] = {}
    prices_by_service: dict[str, set[int]] = {}
    for offer in offers:
        service = str(offer.get("service") or "")
        duration = offer.get("duration_minutes")
        price = int(offer["price"])
        prices_by_service.setdefault(service, set()).add(price)
        if isinstance(duration, int):
            by_service_dur[(service, duration)] = price

    for service, allowed in prices_by_service.items():
        for minute, yen in _service_pairs(text, service):
            if minute is not None:
                expected = by_service_dur.get((service, minute))
                if expected is not None and yen != expected:
                    issues.append(
                        {
                            "field": "copy",
                            "type": "LINKED_FACT",
                            "original": f"{service} {minute}分 = ¥{expected:,}",
                            "generated": f"{service} {minute}分 = ¥{yen:,}",
                            "suggestion": "Keep service, duration and price linked as in the hearing sheet",
                        }
                    )
            elif yen not in allowed:
                issues.append(
                    {
                        "field": "copy",
                        "type": "LINKED_FACT",
                        "original": f"{service} prices {sorted(allowed)}",
                        "generated": f"{service} + ¥{yen:,}",
                        "suggestion": "Do not attach another service's price",
                    }
                )

    source_station = access.get("station") or ""
    source_walk = access.get("walking_minutes")
    for match in re.finditer(r"([一-龯ぁ-んァ-ンA-Za-z0-9]{2,12}駅)", text):
        name = match.group(1)
        if name in GENERIC_STATION_WORDS:
            continue
        local = text[max(0, match.start() - 8) : min(len(text), match.end() + 16)]
        walk = walking_minutes(local)
        if not walk:
            walk = walking_minutes(text[max(0, match.start() - 16) : match.start() + 1])
        if source_station and name == source_station and source_walk is not None and walk is not None:
            if walk != source_walk:
                issues.append(
                    {
                        "field": "station",
                        "type": "LINKED_FACT",
                        "original": f"{source_station} 徒歩{source_walk}分",
                        "generated": f"{name} 徒歩{walk}分",
                        "suggestion": "Keep station and walking time together",
                    }
                )
        if source_walk is not None and walk == source_walk and source_station and name != source_station:
            issues.append(
                {
                    "field": "station",
                    "type": "LINKED_FACT",
                    "original": source_station,
                    "generated": name,
                    "suggestion": "Do not attach the source walking time to another station",
                }
            )

    source_phone = access.get("phone") or ""
    for found in extract_phones(text):
        if source_phone and found != source_phone:
            issues.append(
                {
                    "field": "phone",
                    "type": "SOURCE_MISMATCH",
                    "original": source_phone,
                    "generated": found,
                    "suggestion": "Phone must match the hearing sheet number",
                }
            )

    source_name = access.get("business_name") or ""
    source_addr = access.get("address") or ""
    if source_name and source_addr and source_name in text and "住所" in text:
        if re.search(r"\d{1,4}-\d{1,4}-\d{1,4}", text) and source_addr not in text:
            issues.append(
                {
                    "field": "address",
                    "type": "LINKED_FACT",
                    "original": source_addr,
                    "generated": "",
                    "suggestion": "Business name must stay with the source address",
                }
            )
    return issues


def restore_linked_tbd(text: str, hearing: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Replace 要ヒアリング only when the nearest service+duration uniquely maps to a price."""
    if "要ヒアリング" not in str(text or ""):
        return str(text or ""), []
    repairs: list[dict[str, str]] = []
    offers = parse_offers(hearing)
    by_service_dur: dict[tuple[str, int], int] = {}
    services = []
    for offer in offers:
        service = str(offer.get("service") or "")
        dur = offer.get("duration_minutes")
        if service and isinstance(dur, int):
            by_service_dur[(service, dur)] = int(offer["price"])
            if service not in services:
                services.append(service)
    services.sort(key=len, reverse=True)
    original = str(text)

    def repl(match: re.Match[str]) -> str:
        start = match.start()
        left = original[max(0, start - 48) : start]
        nearest_dur = list(DURATION_RE.finditer(left))
        if not nearest_dur:
            return match.group(0)
        minute = int(nearest_dur[-1].group(1))
        service = next((name for name in services if name in left), "")
        if not service:
            return match.group(0)
        yen = by_service_dur.get((service, minute))
        if yen is None:
            return match.group(0)
        after = f"¥{yen:,}"
        repairs.append(
            {
                "field": "copy",
                "type": "LINKED_FACT_RESTORE",
                "before": match.group(0),
                "after": after,
                "reason": "deterministic restore from nearest service+duration",
                "source_fact": f"{service} {minute}分 = {after}",
            }
        )
        return after

    return re.sub(r"要ヒアリング", repl, original), repairs
