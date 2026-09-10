"""High-risk claim detection and grounding verdicts.

Two layers:
1. Deterministic phrase / category checks (always on).
2. Optional semantic verifier JSON (SUPPORTED / INFERENCE / UNSUPPORTED).
"""

from __future__ import annotations

import re
from typing import Any

from ai_agent.pipeline.facts import copy_blob, hearing_blob

# High-risk spans. support_token must appear in the hearing to keep the claim.
HIGH_RISK: list[tuple[str, str, str]] = [
    # category, pattern, support_token
    ("FACILITY_CLAIM", r"完全個室に近い造り", "個室"),
    ("FACILITY_CLAIM", r"完全個室", "個室"),
    ("FACILITY_CLAIM", r"個室完備", "個室"),
    ("FACILITY_CLAIM", r"個室でのサービス", "個室"),
    ("FACILITY_CLAIM", r"専用駐車場", "専用駐車場"),
    ("QUALIFICATION_CLAIM", r"経験豊富な(?:専門)?スタッフ", "経験豊富"),
    ("QUALIFICATION_CLAIM", r"資格を持つスタッフ", "資格"),
    ("QUALIFICATION_CLAIM", r"専門スタッフ", "専門スタッフ"),
    ("MEDICAL_CLAIM", r"医師監修", "医師監修"),
    ("MEDICAL_CLAIM", r"効果が期待できます", "効果"),
    ("MEDICAL_CLAIM", r"必ず改善します", "必ず改善"),
    ("BUSINESS_PROMISE", r"無理な勧誘は(?:一切)?ありません", "勧誘"),
    ("BUSINESS_PROMISE", r"無理な勧誘なし", "勧誘"),
    ("BUSINESS_PROMISE", r"予約すれば必ず席を確保", "席を確保"),
    ("BUSINESS_PROMISE", r"事前にお席を確保", "席を確保"),
    ("BUSINESS_PROMISE", r"最適なコースをご提案します", "最適なコース"),
    ("BUSINESS_PROMISE", r"最適なコースをお選び", "最適なコース"),
    ("BUSINESS_PROMISE", r"最適な(?:コース|施術|メニュー)をご案内", "最適な"),
    ("BUSINESS_PROMISE", r"体の状態に合わせて施術します", "体の状態に合わせ"),
    ("BUSINESS_PROMISE", r"現在の状態やご希望をお伺い", "現在の状態"),
    ("BUSINESS_PROMISE", r"お体の状態やご希望を事前にお伺い", "お体の状態"),
    ("BUSINESS_PROMISE", r"体調を詳しく確認", "詳しく確認"),
    ("FACILITY_CLAIM", r"心地よい香りに包まれ", "香り"),
    ("FACILITY_CLAIM", r"香りが店内に漂", "香り"),
]

COUNSEL_RESTATE = re.compile(r"初回.{0,12}カウンセリング")
COUNSEL_PROMISE = re.compile(
    r"最適(?:な)?(?:コース|施術|メニュー)をご提案|体調を詳しく|体の状態に合わせ"
)


def freeze_missing(hearing: dict[str, Any]) -> list[str]:
    """Immutable missing[] from the hearing sheet. AI cannot edit this list."""
    out: list[str] = []
    seen: set[str] = set()
    raw = hearing.get("missing") if isinstance(hearing, dict) else []
    if isinstance(raw, str):
        raw = re.split(r"[、,;；\n]+", raw)
    for item in raw or []:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def missing_notice(missing: list[str]) -> str:
    if not missing:
        return ""
    return "・".join(missing) + "は要ヒアリングです。"


def missing_preserved(hearing: dict[str, Any], actual: list[str] | None) -> bool:
    return freeze_missing(hearing) == freeze_missing({"missing": actual or []})


def _supported(token: str, hearing: dict[str, Any]) -> bool:
    if not token:
        return False
    return token in hearing_blob(hearing)


def high_risk_matches(text: str, hearing: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    blob = str(text or "")
    for category, pattern, token in HIGH_RISK:
        if _supported(token, hearing):
            continue
        for match in re.finditer(pattern, blob):
            issues.append(
                {
                    "field": "copy",
                    "type": "UNSUPPORTED",
                    "category": category,
                    "generated": match.group(0),
                    "verdict": "UNSUPPORTED",
                    "suggestion": "Remove claim; not in the hearing sheet",
                }
            )
    return issues


def strip_high_risk_claims(text: str, hearing: dict[str, Any]) -> str:
    out = str(text or "")
    for _category, pattern, token in HIGH_RISK:
        if _supported(token, hearing):
            continue
        out = re.sub(pattern, "", out)
    out = re.sub(r"[、。]{2,}", "。", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" 、")


def ground_statement(statement: str, hearing: dict[str, Any]) -> dict[str, str]:
    """Deterministic grounding verdict for one statement."""
    text = str(statement or "").strip()
    blob = hearing_blob(hearing)
    for category, pattern, token in HIGH_RISK:
        if re.search(pattern, text) and not _supported(token, hearing):
            return {
                "statement": text,
                "verdict": "UNSUPPORTED",
                "category": category,
            }
    if COUNSEL_RESTATE.search(text) and "カウンセリング" in blob:
        if COUNSEL_PROMISE.search(text):
            return {
                "statement": text,
                "verdict": "UNSUPPORTED",
                "category": "BUSINESS_PROMISE",
            }
        return {"statement": text, "verdict": "SUPPORTED", "category": "FACT"}
    if text and text in blob:
        return {"statement": text, "verdict": "SUPPORTED", "category": "FACT"}
    return {"statement": text, "verdict": "INFERENCE", "category": "SAFE_COPY"}


def apply_semantic_verdicts(text: str, claims: list[dict[str, str]]) -> str:
    """Drop UNSUPPORTED spans. Risky INFERENCE (promises/facilities) also drop."""
    out = str(text or "")
    risky = {
        "BUSINESS_PROMISE",
        "FACILITY_CLAIM",
        "QUALIFICATION_CLAIM",
        "MEDICAL_CLAIM",
        "UNSUPPORTED",
        "PRICE_OR_SERVICE_CLAIM",
    }
    for claim in claims:
        verdict = str(claim.get("verdict") or "").upper()
        category = str(claim.get("category") or claim.get("type") or "")
        span = str(claim.get("span") or claim.get("generated") or claim.get("statement") or "")
        if not span or span not in out:
            continue
        drop = verdict == "UNSUPPORTED" or (
            verdict == "INFERENCE" and category in risky
        )
        if drop:
            out = out.replace(span, "", 1)
    return re.sub(r"\s{2,}", " ", out).strip(" 、")


def claim_issues_for_copy(copy: dict[str, Any], hearing: dict[str, Any]) -> list[dict[str, str]]:
    return high_risk_matches(copy_blob(copy), hearing)
