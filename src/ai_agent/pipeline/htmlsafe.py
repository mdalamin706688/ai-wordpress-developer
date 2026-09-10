"""Escape WordPress-bound text. Prose fields are plain text, not HTML."""

from __future__ import annotations

import html
import re
from typing import Any

UNSAFE_ATTR_RE = re.compile(r"\son\w+\s*=", re.I)
JS_URL_RE = re.compile(r"javascript\s*:", re.I)
TAG_RE = re.compile(r"</?(script|iframe|object|embed|style|link|meta|img|svg)\b", re.I)


def escape_wp_text(value: Any) -> str:
    """Plain-text escape. Scripts, event handlers and javascript: URLs cannot survive."""
    text = "" if value is None else str(value)
    text = TAG_RE.sub("", text)
    text = UNSAFE_ATTR_RE.sub(" ", text)
    text = JS_URL_RE.sub("", text)
    return html.escape(text, quote=True)


def sanitize_site_pages(site: dict[str, Any]) -> dict[str, Any]:
    out = dict(site)
    pages = []
    for page in out.get("pages") or []:
        item = dict(page)
        for key in ("title", "heading", "lead", "cta", "notes", "slug", "nav_label"):
            if key in item:
                item[key] = escape_wp_text(item.get(key))
        paras = item.get("body_paragraphs") or []
        if isinstance(paras, list):
            item["body_paragraphs"] = [escape_wp_text(p) for p in paras]
        items = item.get("items") or []
        if isinstance(items, list):
            cleaned_items = []
            for row in items:
                if isinstance(row, dict):
                    cleaned_items.append({k: escape_wp_text(v) for k, v in row.items()})
                else:
                    cleaned_items.append(escape_wp_text(row))
            item["items"] = cleaned_items
        pages.append(item)
    out["pages"] = pages
    out["site_name"] = escape_wp_text(out.get("site_name"))
    menu = out.get("menu") or []
    if isinstance(menu, list):
        out["menu"] = [
            {k: escape_wp_text(v) for k, v in row.items()} if isinstance(row, dict) else escape_wp_text(row)
            for row in menu
        ]
    return out
