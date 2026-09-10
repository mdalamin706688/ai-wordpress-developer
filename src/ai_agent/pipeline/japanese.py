"""Deterministic Japanese syntax checks and conservative post-repair fixes."""

from __future__ import annotations

import re
from typing import Any

from ai_agent.pipeline.facts import restore_station_walk, station_short_name, yen_digits
from ai_agent.pipeline.linked import linked_fact_issues
from ai_agent.pipeline.normalize import walking_minutes

CRITICAL_PATTERNS: list[tuple[str, str, str]] = [
    (
        r"(^|[。！？\n])\s*(?:から|より)徒歩\s*[0-9０-９]+\s*分",
        "JAPANESE_GRAMMAR",
        "Walking time is missing its station/subject",
    ),
    (
        r"(^|[。！？\n])\s*は[東西南北一-龯ぁ-んァ-ンA-Za-z]",
        "JAPANESE_GRAMMAR",
        "Sentence starts with は (missing subject)",
    ),
    (r"ではは|にはは|とはは|ではは", "JAPANESE_GRAMMAR", "Duplicated particle"),
    (r"ご利用いただけますできます", "JAPANESE_GRAMMAR", "Duplicated predicate"),
    (r"できますできます", "JAPANESE_GRAMMAR", "Duplicated できます"),
    (r"にありますです", "JAPANESE_GRAMMAR", "Broken にありますです join"),
    (r"ですです", "JAPANESE_GRAMMAR", "Duplicated です"),
    (r"。の(?=[東西南北一-龯])", "JAPANESE_GRAMMAR", "Broken join after deletion (。の)"),
]

ENGLISH_ARTIFACT = re.compile(
    r"\b(as an AI|lorem ipsum|TODO|FIXME|null\b|undefined)\b", re.I
)
LIST_LEAK = re.compile(r"^\s*[-*]\s+|^\s*\d+\.\s+", re.M)


def japanese_grammar_issues(text: str, *, field: str = "copy") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    raw = str(text or "")
    if not raw.strip():
        return issues
    for pattern, kind, suggestion in CRITICAL_PATTERNS:
        match = re.search(pattern, raw)
        if match:
            issues.append(
                {
                    "field": field,
                    "type": kind,
                    "span": match.group(0)[:80],
                    "generated": match.group(0)[:80],
                    "suggestion": suggestion,
                    "severity": "critical",
                }
            )
    if ENGLISH_ARTIFACT.search(raw):
        issues.append(
            {
                "field": field,
                "type": "JAPANESE_GRAMMAR",
                "span": "english/model artifact",
                "generated": ENGLISH_ARTIFACT.search(raw).group(0),
                "suggestion": "Remove English/model artifacts",
                "severity": "critical",
            }
        )
    if LIST_LEAK.search(raw) and ("[" in raw or raw.lstrip().startswith(("-", "*"))):
        issues.append(
            {
                "field": field,
                "type": "JAPANESE_GRAMMAR",
                "span": raw[:40],
                "generated": raw[:40],
                "suggestion": "Prose fields must not be markdown lists",
                "severity": "warning",
            }
        )
    return issues


def grammar_issues_for_copy(copy: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for key in ("title", "heading", "lead", "cta"):
        issues.extend(japanese_grammar_issues(str(copy.get(key) or ""), field=key))
    paras = copy.get("body_paragraphs") or []
    if isinstance(paras, list):
        for i, para in enumerate(paras):
            issues.extend(japanese_grammar_issues(str(para), field=f"body_{i + 1}"))
    return issues


def _fingerprint(text: str, hearing: dict[str, Any]) -> tuple:
    station = station_short_name(str(hearing.get("station") or ""))
    return (
        frozenset(yen_digits(text)),
        walking_minutes(text),
        station in (text or "") if station else True,
        str(hearing.get("phone") or "") in (text or "") or not str(hearing.get("phone") or ""),
    )


def repair_japanese_text(text: str, hearing: dict[str, Any]) -> str:
    """Conservative syntax fixes. Must not change protected facts."""
    before = str(text or "")
    out = restore_station_walk(before, hearing)
    out = re.sub(r"ではは", "では", out)
    out = re.sub(r"にはは", "には", out)
    out = re.sub(r"とはは", "とは", out)
    out = re.sub(r"ご利用いただけますできます", "ご利用いただけます", out)
    out = re.sub(r"できますできます", "できます", out)
    out = re.sub(r"にありますです", "にあります", out)
    out = re.sub(r"ですです", "です", out)
    out = re.sub(r"。の(?=[東西南北一-龯])", "。", out)
    # Sentence starting with は + known line/station.
    station = str(hearing.get("station") or "")
    name = station_short_name(station)
    if name and re.match(r"^は" + re.escape(name), out):
        out = "最寄り駅" + out
    elif name and re.match(r"^は東急", out):
        out = "最寄り駅" + out
    elif re.search(r"(^|[。！？\n])は東急", out) and name:
        out = re.sub(r"(^|[。！？\n])は東急", r"\1最寄り駅は東急", out, count=1)
    after_issues = linked_fact_issues(out, hearing)
    before_issues = linked_fact_issues(before, hearing)
    if after_issues and len(after_issues) > len(before_issues):
        return before
    if _fingerprint(out, hearing) != _fingerprint(before, hearing) and yen_digits(before):
        # Walk/station restore is allowed to add the station name.
        if not (name and name in out):
            return before
    return out


def repair_copy_grammar(copy: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    out = dict(copy)
    for key in ("title", "heading", "lead", "cta", "notes"):
        out[key] = repair_japanese_text(str(out.get(key) or ""), hearing)
    paras = out.get("body_paragraphs") or []
    if isinstance(paras, list):
        out["body_paragraphs"] = [repair_japanese_text(str(p), hearing) for p in paras]
    return out
