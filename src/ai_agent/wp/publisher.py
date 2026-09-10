"""WordPress page writes: draft-only before human approval, no partial success."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from ai_agent.pipeline.htmlsafe import escape_wp_text
from ai_agent.pipeline.observability import pipeline_log
from ai_agent.wp.client import WordPressClient

FORBIDDEN_WP_STATUSES = frozenset({"publish", "future", "private", "pending"})


class HttpTransport(Protocol):
    def request(self, method: str, path: str, **kwargs: Any) -> Any: ...


def publishing_guard(*, human_approved: bool, requested_status: str = "draft") -> str:
    """Trusted application logic owns publish state. Models cannot approve."""
    if not human_approved:
        return "draft"
    requested = str(requested_status or "draft").lower()
    if requested in FORBIDDEN_WP_STATUSES or requested != "draft":
        return "draft"
    return "draft"


def idempotency_slug(job_id: str, page_slug: str) -> str:
    token = hashlib.sha256(f"{job_id}:{page_slug}".encode("utf-8")).hexdigest()[:10]
    base = "".join(ch for ch in str(page_slug or "page") if ch.isalnum() or ch in "-_")[:40] or "page"
    return f"{base}-{token}"


def page_payload(
    page: dict[str, Any],
    *,
    job_id: str,
    human_approved: bool = False,
) -> dict[str, Any]:
    status = publishing_guard(
        human_approved=human_approved,
        requested_status=str(page.get("status") or "draft"),
    )
    if status in FORBIDDEN_WP_STATUSES:
        status = "draft"
    content_parts = [str(page.get("lead") or "")]
    for para in page.get("body_paragraphs") or []:
        content_parts.append(str(para))
    content = "\n\n".join(part for part in content_parts if str(part).strip())
    return {
        "title": escape_wp_text(page.get("title") or ""),
        "slug": idempotency_slug(job_id, str(page.get("slug") or page.get("id") or "page")),
        "status": status,
        "content": escape_wp_text(content),
        "meta": {"bbs_job_id": job_id, "bbs_page_id": str(page.get("id") or "")},
    }


def _response_json(response: Any) -> dict[str, Any]:
    if hasattr(response, "json"):
        try:
            data = response.json()
            return data if isinstance(data, dict) else {"raw": data}
        except Exception:
            return {}
    if isinstance(response, dict):
        return response
    return {}


def create_draft_pages(
    site: dict[str, Any],
    *,
    job_id: str,
    human_approved: bool = False,
    client: WordPressClient | HttpTransport | None = None,
    transport: HttpTransport | None = None,
) -> dict[str, Any]:
    """Validate every page, then write. Never report full success on a partial write."""
    if human_approved is not True:
        human_approved = False
    pages = list(site.get("pages") or [])
    payloads = [page_payload(page, job_id=job_id, human_approved=human_approved) for page in pages]
    for payload in payloads:
        if payload.get("status") != "draft":
            return {
                "ok": False,
                "partial": False,
                "created": [],
                "error": "publishing_guard_blocked_non_draft",
                "wordpress_status": "blocked",
            }
        if not payload.get("title"):
            return {
                "ok": False,
                "partial": False,
                "created": [],
                "error": "invalid_page_payload",
                "wordpress_status": "blocked",
            }

    writer = transport or client
    if writer is None:
        return {
            "ok": True,
            "dry_run": True,
            "partial": False,
            "created": [],
            "payloads": payloads,
            "wordpress_status": "draft",
        }

    created: list[dict[str, Any]] = []
    for payload in payloads:
        try:
            existing = writer.request(
                "GET",
                "wp/v2/pages",
                params={"slug": payload["slug"], "status": "any"},
            )
            rows = existing.json() if hasattr(existing, "json") else existing
            if isinstance(rows, list) and rows:
                created.append(
                    {
                        "id": rows[0].get("id") if isinstance(rows[0], dict) else None,
                        "slug": payload["slug"],
                        "idempotent": True,
                        "status": "draft",
                    }
                )
                continue
            response = writer.request("POST", "wp/v2/pages", json=payload)
            status_code = getattr(response, "status_code", 201)
            if int(status_code) >= 400:
                return {
                    "ok": False,
                    "partial": bool(created),
                    "created": created,
                    "error": f"wordpress_http_{status_code}",
                    "wordpress_status": "partial" if created else "failed",
                    "payloads": payloads,
                }
            body = _response_json(response)
            created.append(
                {
                    "id": body.get("id"),
                    "slug": payload["slug"],
                    "idempotent": False,
                    "status": "draft",
                }
            )
        except Exception as exc:
            pipeline_log(
                job_id=job_id,
                stage="wordpress",
                validation_status="FAILED",
                wordpress_status="partial" if created else "failed",
                extra=type(exc).__name__,
            )
            return {
                "ok": False,
                "partial": bool(created),
                "created": created,
                "error": "wordpress_write_failed",
                "wordpress_status": "partial" if created else "failed",
                "payloads": payloads,
            }

    pipeline_log(
        job_id=job_id,
        stage="wordpress",
        validation_status="PASS",
        wordpress_status="draft",
        extra=f"pages={len(created)}",
    )
    return {
        "ok": True,
        "partial": False,
        "created": created,
        "wordpress_status": "draft",
        "payloads": payloads,
    }
