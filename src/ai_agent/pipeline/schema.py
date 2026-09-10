"""Normalize homepage copy into a fixed schema. Structured fields are sealed from the hearing."""

from __future__ import annotations

import re
from typing import Any

COPY_KEYS = ("title", "slug", "heading", "lead", "body_paragraphs", "cta", "notes")
PRIVILEGED_KEYS = frozenset(
    {"publish_allowed", "published", "status", "human_approved", "approval", "wordpress_status"}
)
PARA_COUNT = 6

LIST_LEAK_RE = re.compile(r"^\s*\[(['\"].*['\"]\s*,|\s*')")
JSON_ARRAY_RE = re.compile(r"^\s*\[")
JSON_OBJECT_RE = re.compile(r"^\s*\{")


class SchemaError(ValueError):
    """Malformed AI output. Do not coerce into publishable prose."""

    def __init__(self, message: str, *, field: str = "") -> None:
        super().__init__(message)
        self.field = field
        self.code = "SCHEMA_ERROR"


def looks_like_serialized_structure(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if LIST_LEAK_RE.match(s):
        return True
    if JSON_ARRAY_RE.match(s) and s.endswith("]"):
        return True
    if JSON_OBJECT_RE.match(s) and s.endswith("}"):
        return True
    return False


def _markdown_only(text: str) -> str:
    return re.sub(r"[*_`#]+", "", text or "").strip()


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return str(value)
    return _markdown_only(str(value))


def assert_copy_schema(data: dict[str, Any]) -> None:
    """Fail closed on invalid AI field types. Never guess intended prose."""
    if not isinstance(data, dict):
        raise SchemaError("copy JSON must be an object")
    extra = [key for key in data if key not in COPY_KEYS and key not in PRIVILEGED_KEYS]
    nested_extra = [key for key in extra if isinstance(data.get(key), (dict, list))]
    if nested_extra:
        raise SchemaError(
            f"unexpected nested field: {nested_extra[0]}",
            field=nested_extra[0],
        )
    for key in COPY_KEYS:
        if key not in data:
            continue
        val = data[key]
        if key == "body_paragraphs":
            if val is None:
                raise SchemaError("body_paragraphs must be a list of strings", field=key)
            if not isinstance(val, list):
                raise SchemaError("body_paragraphs must be a list of strings", field=key)
            for i, para in enumerate(val):
                if para is None or isinstance(para, (list, dict)):
                    raise SchemaError(
                        "body paragraph must be a string",
                        field=f"body_{i + 1}",
                    )
                if looks_like_serialized_structure(str(para)):
                    raise SchemaError(
                        "WordPress field must be a plain string, not a Python/JSON list",
                        field=f"body_{i + 1}",
                    )
            continue
        if val is None:
            raise SchemaError(f"{key} must be a string", field=key)
        if isinstance(val, (list, dict)):
            raise SchemaError(f"{key} must be a plain string", field=key)
        if looks_like_serialized_structure(str(val)):
            raise SchemaError(
                "WordPress field must be a plain string, not a Python/JSON list",
                field=key,
            )


def _plain_paragraphs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_markdown_only(str(item)) for item in value if str(item).strip()]


def normalize_copy(copy: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(copy or {})
    cleaned = _plain_paragraphs(data.get("body_paragraphs"))
    while len(cleaned) < PARA_COUNT:
        cleaned.append("")
    return {
        "title": _plain_text(data.get("title")),
        "slug": _plain_text(data.get("slug")) or "top",
        "heading": _plain_text(data.get("heading")),
        "lead": _plain_text(data.get("lead")),
        "body_paragraphs": cleaned[:PARA_COUNT],
        "cta": _plain_text(data.get("cta")) or "ご予約はこちら",
        "notes": _plain_text(data.get("notes")),
    }


def seal_structured_fields(copy: dict[str, Any], hearing: dict[str, Any]) -> dict[str, Any]:
    """Fill title/slug/cta from the hearing so the model cannot invent them."""
    out = normalize_copy(copy)
    name = str(hearing.get("business_name") or "").strip()
    area = str(hearing.get("area") or hearing.get("station") or "").strip()
    industry = "リラクゼーション" if "salon" in str(hearing.get("industry") or "") else ""
    if name:
        suffix = area or industry or "公式サイト"
        out["title"] = f"{name}｜{suffix}"
    out["slug"] = "top"
    page_intent = str(hearing.get("target_page") or "").lower()
    slug_map = {
        "service": "service",
        "services": "service",
        "concept": "concept",
        "greeting": "greeting",
        "menu": "menu",
        "faq": "faq",
        "feature": "feature",
        "access": "access",
        "reviews": "reviews",
        "blog": "blog",
        "column": "column",
    }
    if page_intent in slug_map:
        out["slug"] = slug_map[page_intent]
    catch = str(hearing.get("catchcopy") or "").strip()
    if 10 <= len(catch) <= 36 and out["slug"] == "top":
        out["heading"] = catch
    reservation = str(hearing.get("reservation") or "").strip()
    if reservation and len(reservation) <= 24:
        out["cta"] = "ご予約はこちら"
    elif not out["cta"]:
        out["cta"] = "ご予約はこちら"
    return out
