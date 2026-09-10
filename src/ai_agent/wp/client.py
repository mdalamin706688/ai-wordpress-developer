from __future__ import annotations

from urllib.parse import urljoin

import httpx

from ai_agent.config import get_settings


class WordPressClient:
    """REST client. Uses ?rest_route= because fresh sites have empty permalinks."""

    def __init__(
        self,
        site_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        rest_path_style: str = "rest_route",
    ) -> None:
        settings = get_settings()
        self.site_url = (site_url or settings.wp_site_url).rstrip("/")
        self.user = user or settings.wp_user
        self.password = password or settings.wp_app_password
        self.rest_path_style = rest_path_style

    def configured(self) -> bool:
        return bool(self.site_url and self.user and self.password)

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        if self.rest_path_style == "pretty":
            return urljoin(self.site_url + "/", f"wp-json/{path}")
        return f"{self.site_url}/?rest_route=/{path}"

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.configured():
            raise RuntimeError("WordPress target is not configured")
        with httpx.Client(timeout=30.0) as client:
            return client.request(
                method,
                self._url(path),
                auth=(self.user, self.password),
                **kwargs,
            )

    def ping(self) -> dict:
        response = self.request("GET", "wp/v2/types")
        response.raise_for_status()
        return {"ok": True, "status_code": response.status_code}

    def create_page(self, payload: dict) -> dict:
        """Create a page. Status is forced to draft by the publisher guard."""
        from ai_agent.wp.publisher import publishing_guard

        body = dict(payload or {})
        body["status"] = publishing_guard(
            human_approved=False,
            requested_status=str(body.get("status") or "draft"),
        )
        response = self.request("POST", "wp/v2/pages", json=body)
        response.raise_for_status()
        return response.json()
