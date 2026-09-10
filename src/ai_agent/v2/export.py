"""Export v2 blueprint/sections to CSV and spreadsheet."""

from __future__ import annotations

import csv
import io
from typing import Any


def blueprint_to_section_rows(blueprint: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten blueprint pages → export rows (before AI-2 content)."""
    rows: list[dict[str, str]] = []
    site = str(blueprint.get("site_name") or "")

    def add_page(page: dict[str, Any], *, group: str = "page") -> None:
        pid = str(page.get("id") or "")
        slug = str(page.get("slug") or "")
        for sec in page.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            rows.append(
                {
                    "site": site,
                    "group": group,
                    "page_id": pid,
                    "page_slug": slug,
                    "page_type": str(page.get("type") or ""),
                    "section_id": str(sec.get("id") or ""),
                    "section_label": str(sec.get("label") or ""),
                    "mode": str(sec.get("mode") or ""),
                    "text": "",
                    "seeds": " | ".join(page.get("content_seeds") or [])[:500],
                }
            )

    for page in blueprint.get("pages") or []:
        if isinstance(page, dict):
            add_page(page, group="page")
    for page in blueprint.get("seo_pages") or []:
        if isinstance(page, dict):
            add_page(page, group="seo")
    for page in blueprint.get("tag_pages") or []:
        if isinstance(page, dict):
            add_page(page, group="tag")
    return rows


def sections_to_csv(rows: list[dict[str, str]]) -> str:
    fields = [
        "site",
        "group",
        "page_id",
        "page_slug",
        "page_type",
        "section_id",
        "section_label",
        "mode",
        "text",
        "seeds",
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k, "") for k in fields})
    return buf.getvalue()


def _group_label(group: str) -> str:
    g = (group or "").lower()
    if g in {"page", "nav"}:
        return "ナビ"
    if g == "seo":
        return "SEO"
    if g == "tag":
        return "タグ"
    return group or ""


def _section_fields() -> list[str]:
    return [
        "site",
        "group",
        "page_id",
        "page_slug",
        "page_type",
        "section_id",
        "section_label",
        "mode",
        "text",
        "seeds",
    ]


def _section_headers_jp() -> list[str]:
    return [
        "サイト",
        "区分",
        "ページID",
        "スラッグ",
        "ページ種別",
        "セクションID",
        "セクション名",
        "モード",
        "本文",
        "シード",
    ]


def _write_section_sheet(ws: Any, rows: list[dict[str, str]]) -> None:
    fields = _section_fields()
    ws.append(_section_headers_jp())
    for row in rows:
        out = []
        for f in fields:
            if f == "group":
                out.append(_group_label(str(row.get(f) or "")))
            else:
                out.append(row.get(f, ""))
        ws.append(out)


def sections_to_xlsx_bytes(rows: list[dict[str, str]], *, blueprint: dict[str, Any] | None = None) -> bytes:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for spreadsheet export") from exc

    bp = blueprint or {}
    fields = _section_fields()

    # Page inventory
    page_map: dict[str, dict[str, Any]] = {}
    page_order: list[str] = []
    for row in rows:
        key = f"{row.get('group')}|{row.get('page_id') or row.get('page_slug')}"
        if key not in page_map:
            page_map[key] = {
                "group": _group_label(str(row.get("group") or "")),
                "page_id": row.get("page_id") or "",
                "page_slug": row.get("page_slug") or "",
                "page_type": row.get("page_type") or "",
                "section_count": 0,
                "filled_count": 0,
            }
            page_order.append(key)
        page_map[key]["section_count"] += 1
        if str(row.get("text") or "").strip():
            page_map[key]["filled_count"] += 1

    counts = {"nav": 0, "seo": 0, "tag": 0}
    for key in page_order:
        g = page_map[key]["group"]
        if g == "ナビ":
            counts["nav"] += 1
        elif g == "SEO":
            counts["seo"] += 1
        elif g == "タグ":
            counts["tag"] += 1
    filled = sum(1 for r in rows if str(r.get("text") or "").strip())

    wb = Workbook()
    ws_sum = wb.active
    ws_sum.title = "Overview"
    ws_sum.append(["BBS-CMS · Site Content Export", ""])
    ws_sum.append(["サイト名", bp.get("site_name") or ""])
    ws_sum.append(["制作タイプ", bp.get("production_label") or bp.get("production_type") or ""])
    ws_sum.append(["クローンモード", bp.get("clone_mode") or ""])
    ws_sum.append(["ページ数（合計）", len(page_order)])
    ws_sum.append(["ナビページ", counts["nav"]])
    ws_sum.append(["SEOページ", counts["seo"]])
    ws_sum.append(["タグページ", counts["tag"]])
    ws_sum.append(["セクション行", len(rows)])
    ws_sum.append(["本文あり", filled])
    ws_sum.append(["", ""])
    ws_sum.append(["Overview", "案件サマリー"])
    ws_sum.append(["Pages", "ページ一覧"])
    ws_sum.append(["ナビ / SEO / タグ", "区分ごとのセクション本文"])
    ws_sum.append(["All", "全セクション統合"])
    stats = bp.get("stats") or {}
    if stats:
        ws_sum.append(["", ""])
        ws_sum.append(["Blueprint stats", ""])
        for k, v in stats.items():
            ws_sum.append([k, v])

    ws_pages = wb.create_sheet("Pages")
    ws_pages.append(["区分", "ページID", "スラッグ", "ページ種別", "セクション数", "本文あり"])
    for key in page_order:
        p = page_map[key]
        ws_pages.append(
            [p["group"], p["page_id"], p["page_slug"], p["page_type"], p["section_count"], p["filled_count"]]
        )

    nav_rows = [r for r in rows if str(r.get("group") or "").lower() in {"page", "nav"}]
    seo_rows = [r for r in rows if str(r.get("group") or "").lower() == "seo"]
    tag_rows = [r for r in rows if str(r.get("group") or "").lower() == "tag"]
    if nav_rows:
        _write_section_sheet(wb.create_sheet("ナビ"), nav_rows)
    if seo_rows:
        _write_section_sheet(wb.create_sheet("SEO"), seo_rows)
    if tag_rows:
        _write_section_sheet(wb.create_sheet("タグ"), tag_rows)

    _write_section_sheet(wb.create_sheet("All"), rows)

    # Keep machine-readable CSV-compatible sheet for pipelines
    ws_raw = wb.create_sheet("Raw")
    ws_raw.append(fields)
    for row in rows:
        ws_raw.append([row.get(f, "") for f in fields])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
