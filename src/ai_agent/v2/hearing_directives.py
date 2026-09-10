"""Parse hearing remarks into per-page directives (FAQ URL, blank menu, etc.)."""

from __future__ import annotations

import re
from typing import Any

_URL_RE = re.compile(r"https?://[^\s\)\]、<>\"']+")


def _urls(text: str) -> list[str]:
    return [u.rstrip(".,;") for u in _URL_RE.findall(str(text or ""))]


def writing_push_points(writing_notes: str) -> list[str]:
    """Extract ■ / ・ push bullets from ライティング備考 for AI-2 seeds."""
    text = str(writing_notes or "")
    if not text:
        return []
    points: list[str] = []
    # Split on common bullet markers used in BBS writing notes
    for part in re.split(r"[■●▪]|/(?=\s)|(?<=。)・", text):
        chunk = part.strip(" ・\n\t　「」\"'")
        if not chunk or len(chunk) < 2:
            continue
        if chunk.startswith("http") or "drive.google" in chunk:
            continue
        if "録音" in chunk and "ヒアリング" in chunk and len(chunk) < 40:
            continue
        # Keep short push lines; trim long preamble
        if "推していきたい" in chunk or "下記の内容" in chunk:
            continue
        if "初めての方へページ" in chunk:
            continue
        # Expand bare 「保証」 customer ask into a writable appeal line
        if chunk == "保証" or (chunk.startswith("保証") and "お客様希望" in chunk):
            chunk = "保証対応あり"
        points.append(chunk[:180])
    # Also catch explicit phrases even without clean bullets
    for phrase, expanded in (
        ("見積もり無料", "見積もり無料"),
        ("見積無料", "見積無料"),
        ("保証", "保証対応あり"),
    ):
        if phrase in text and not any(phrase in p or expanded in p for p in points):
            points.append(expanded)
    if "相談" in text and not any("相談" in p for p in points):
        points.append("悩んだらまず相談してほしい、困ったときの強い味方")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in points:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:8]


def _extract_marked_block(text: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    idx = text.find(start_marker)
    if idx < 0:
        return ""
    body = text[idx + len(start_marker) :]
    end_at = len(body)
    for marker in end_markers:
        pos = body.find(marker)
        if pos >= 0:
            end_at = min(end_at, pos)
    return body[:end_at].strip(" -\n\t　")


def company_page_request(remarks: str) -> dict[str, Any] | None:
    """Detect アクセス→会社概要/company rename + bottom content from 備考."""
    rem = str(remarks or "")
    if "会社概要" not in rem:
        return None
    if not re.search(r"ディレクトリ名\s*[:：]\s*company", rem, re.I) and "company" not in rem.lower():
        return None
    seeds: list[str] = []
    block = _extract_marked_block(
        rem,
        "ページ下部に下記内容の入れ込みお願いします。",
        ("《詳しくはこちら》", "■メニュー", "■エアコン", "■デザイン"),
    )
    if not block:
        block = _extract_marked_block(
            rem,
            "----------------------------------",
            ("----------------------------------", "《詳しくはこちら》", "■メニュー"),
        )
    if block:
        # Keep a usable seed without dumping the entire remarks file
        cleaned = re.sub(r"-{5,}", " ", block)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            seeds.append(cleaned[:900])
    if "denki-walker" in rem.lower() or "電気walker" in rem:
        seeds.append("生涯学習型コミュニティ 電気walker（https://denki-walker.net/）")
    return {
        "slug": "company",
        "nav_label": "会社概要",
        "extra_seeds": seeds,
        "reason": "ヒアリング備考: アクセスを会社概要(company)として追加",
    }


def about_business_seeds(remarks: str) -> list[str]:
    """Pull 【業務内容】 insert block for 初めての方へ / about."""
    rem = str(remarks or "")
    if "初めての方" not in rem and "業務内容" not in rem:
        return []
    block = _extract_marked_block(
        rem,
        "【業務内容】",
        ("・ページ下部", "■施工", "■ブログ", "■アクセス", "----------------------------------"),
    )
    if not block:
        return []
    cleaned = re.sub(r"\s+", " ", block).strip()
    if not cleaned:
        return []
    # Chunk into readable seeds for AI-2 (avoid one giant line only)
    seeds: list[str] = ["業務内容（ヒアリング備考より）"]
    for part in re.split(r"[《》]", cleaned):
        part = part.strip(" ：:・")
        if len(part) >= 8:
            seeds.append(part[:220])
    if len(seeds) == 1:
        seeds.append(cleaned[:500])
    return seeds[:12]


def _faq_url_from_text(text: str) -> str:
    for url in _urls(text):
        if "faq" in url.lower():
            return url
    return ""


def parse_page_directives(
    *,
    remarks: str = "",
    writing_notes: str = "",
    pages: list[dict[str, Any]] | None = None,
    reference_sites: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Map page slug → directive flags from hearing text + page slot patterns."""
    out: dict[str, dict[str, Any]] = {}
    rem = str(remarks or "")
    wnotes = str(writing_notes or "")
    combined = f"{rem}\n{wnotes}"

    if rem and ("メニュー" in rem or "料金表" in rem) and "空白" in rem:
        out["menu"] = {
            "leave_blank": True,
            "reason": "ヒアリング備考: メニュー/料金表は空白指定のためサイト構成から除外",
        }

    faq_url = _faq_url_from_text(combined)
    if rem and ("よくある質問" in rem or "FAQ" in rem.upper()) and faq_url:
        out["faq"] = {
            "reference_url": faq_url,
            "reason": "ヒアリング備考: 既存FAQページの内容を参照",
        }

    # Renewal: 初めての方へ / about rewrite from writing notes + Drive URL
    if wnotes and ("初めての方" in wnotes or "about" in wnotes.lower()):
        for url in _urls(wnotes):
            if "drive.google" in url or "docs.google" in url or url:
                out.setdefault(
                    "about",
                    {
                        "reference_url": url,
                        "reason": "ライティング備考: 初めての方へページを参考資料に沿ってリライト",
                    },
                )
                break

    about_seeds = about_business_seeds(rem)
    if about_seeds:
        about_dir = out.setdefault("about", {})
        existing = list(about_dir.get("extra_seeds") or [])
        for s in about_seeds:
            if s not in existing:
                existing.append(s)
        about_dir["extra_seeds"] = existing
        about_dir.setdefault("reason", "ヒアリング備考: 初めての方へへ業務内容を入れ込み")

    company = company_page_request(rem)
    if company:
        out["_company_page"] = company

    if wnotes and "コンセプト" in wnotes:
        for url in _urls(wnotes):
            out.setdefault(
                "concept",
                {
                    "reference_url": url,
                    "reason": "ライティング備考: コンセプトページ参考URL",
                },
            )
            break

    for page in pages or []:
        if not isinstance(page, dict):
            continue
        slug = str(page.get("slug") or "").strip()
        ptype = str(page.get("type") or "")
        items = [str(x).strip() for x in (page.get("items") or []) if str(x).strip()]

        if ptype == "メニュー (総合)" and slug == "menu" and not items:
            out.setdefault(
                "menu",
                {
                    "leave_blank": True,
                    "reason": "ヒアリング: 料金表に項目内容なし — ページをサイト構成から除外",
                },
            )

        if ptype == "よくある質問" and slug == "faq" and not items and slug not in out:
            url = faq_url
            if not url:
                for ref in reference_sites or []:
                    if not isinstance(ref, dict):
                        continue
                    candidate = str(ref.get("url") or "")
                    base = candidate.rstrip("/")
                    if base:
                        url = f"{base}/FAQ/"
                        break
            if url:
                out["faq"] = {
                    "reference_url": url,
                    "reason": "ヒアリング: FAQスロット空欄 — 既存サイトFAQを参照",
                }

    return out


def apply_directives_to_pages(pages: list[dict[str, Any]], directives: dict[str, dict[str, Any]]) -> None:
    """Attach directive flags onto blueprint page dicts (in place)."""
    for page in pages:
        if not isinstance(page, dict):
            continue
        slug = str(page.get("slug") or page.get("id") or "")
        d = directives.get(slug) or {}
        if d.get("leave_blank"):
            page["leave_blank"] = True
            page["leave_blank_reason"] = str(d.get("reason") or "")
        ref = str(d.get("reference_url") or "").strip()
        if ref:
            page["reference_url"] = ref
            page["reference_note"] = str(d.get("reason") or "")
        seeds = d.get("extra_seeds")
        if isinstance(seeds, list) and seeds:
            merged = list(page.get("content_seeds") or [])
            for s in seeds:
                s = str(s or "").strip()
                if s and s not in merged:
                    merged.append(s)
            page["content_seeds"] = merged


def attach_writing_push_seeds(pages: list[dict[str, Any]], hearing: dict[str, Any]) -> None:
    """Merge ライティング備考 push points into about / estimates / home seeds."""
    wg = hearing.get("writing_guidance") or {}
    points = writing_push_points(str(wg.get("writing_notes") or ""))
    if not points:
        return
    targets = {"about", "estimates", "home", "concept"}
    for page in pages:
        if not isinstance(page, dict):
            continue
        slug = str(page.get("slug") or "")
        if slug not in targets:
            continue
        merged = list(page.get("content_seeds") or [])
        for p in points:
            if p not in merged:
                merged.append(p)
        page["content_seeds"] = merged
        # Keep a short rule hint for AI-2
        page["writing_push_points"] = list(points)
