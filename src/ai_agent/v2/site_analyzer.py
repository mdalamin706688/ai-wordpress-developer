"""Fetch hearing reference / main / existing URLs and extract STRUCTURE (not copy).

Used for Type 2–4 when live links exist. AI-1 uses nav + section patterns;
AI-2 may use short heading topic hints — never paste live body paragraphs.
Hearing sheet remains the source of truth for facts.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

_USER_AGENT = (
    "BBS-CMS-AI-SiteAnalyzer/1.0 (+structure-only; https://bbs-cms.local)"
)
_MAX_PAGES = 10
_MAX_BYTES = 800_000
_TIMEOUT = 12.0
_SKIP_PATH_PARTS = (
    "/blog/",
    "/column/",
    "/news/",
    "/wp-admin",
    "/wp-json",
    "/feed",
    "/tag/",
    "/category/",
    "/author/",
    ".pdf",
    ".jpg",
    ".png",
    ".css",
    ".js",
)

# Map common Japanese / English nav labels and path segments → our page types/slugs
_NAV_TO_SLUG: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(top|home|トップ|ホーム)$", re.I), "home"),
    (re.compile(r"concept|コンセプト|初めて|想い|理念", re.I), "concept"),
    (re.compile(r"service|サービス|メニュー|料金|工事|施工内容", re.I), "service"),
    (re.compile(r"faq|よくある質問|Ｑ＆Ａ|Q&A", re.I), "faq"),
    (re.compile(r"greeting|あいさつ|挨拶|代表|ご挨拶", re.I), "greeting"),
    (re.compile(r"staff|スタッフ|職人", re.I), "staff"),
    (re.compile(r"review|voice|お客様の声|口コミ|レビュー", re.I), "reviews"),
    (re.compile(r"access|アクセス|会社概要|company", re.I), "access"),
    (re.compile(r"contact|contact|お問い合わせ|ご予約|予約|フォーム", re.I), "contact"),
    (re.compile(r"recruit|求人|採用", re.I), "recruit"),
    (re.compile(r"blog|ブログ", re.I), "blog"),
    (re.compile(r"column|コラム", re.I), "column"),
    (re.compile(r"gallery|works|施工事例|実績|ギャラリー", re.I), "gallery"),
    (re.compile(r"price|料金|価格", re.I), "price"),
]


def live_site_analyze_enabled() -> bool:
    # Unit tests skip network unless explicitly enabled.
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("BBS_LIVE_SITE_ANALYZE", "") != "1":
        return False
    raw = str(os.environ.get("BBS_LIVE_SITE_ANALYZE", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _s(value: Any) -> str:
    return str(value or "").strip()


def _normalize_url(url: str) -> str:
    u = _s(url)
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/") + ("/" if urlparse(u).path in {"", "/"} else "")


def collect_live_urls(hearing: dict[str, Any]) -> list[dict[str, str]]:
    """Collect analyzable URLs from hearing (main site, references, existing, page refs)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: str, role: str) -> None:
        u = _normalize_url(url)
        if not u or u in seen:
            return
        if "drive.google" in u or "docs.google" in u or "hearing-sys" in u:
            return
        seen.add(u)
        out.append({"url": u, "role": role})

    project = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    add(_s(project.get("existing_url")), "existing")

    for ref in hearing.get("reference_sites") or []:
        if not isinstance(ref, dict):
            continue
        kind = _s(ref.get("kind"))
        url = _s(ref.get("url"))
        role = "main_site" if "お客様所有" in kind else "reference"
        add(url, role)

    for slot in hearing.get("pages") or []:
        if not isinstance(slot, dict):
            continue
        # page items sometimes contain URLs
        for item in slot.get("items") or []:
            m = re.search(r"https?://[^\s\)\]、<>\"']+", str(item or ""))
            if m:
                add(m.group(0), "page_seed")

    directives = hearing.get("page_directives") if isinstance(hearing.get("page_directives"), dict) else {}
    for key, block in directives.items():
        if not isinstance(block, dict):
            continue
        add(_s(block.get("reference_url")), f"directive:{key}")

    return out


class _PageHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self._in_title = False
        self._in_script = False
        self._in_style = False
        self._capture_heading: str | None = None
        self.headings: list[dict[str, str]] = []
        self.links: list[tuple[str, str]] = []  # (href, text)
        self._link_href: str | None = None
        self._link_text: list[str] = []
        self._text_chunks: list[str] = []
        self._current_tag: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        self._current_tag = tag
        if tag in {"script", "style", "noscript"}:
            if tag == "style":
                self._in_style = True
            else:
                self._in_script = True
            return
        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2", "h3"}:
            self._capture_heading = tag
            self._heading_buf = []
        if tag == "a":
            href = ad.get("href", "")
            if href:
                self._link_href = href
                self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" or tag == "noscript":
            self._in_script = False
        if tag == "style":
            self._in_style = False
        if tag == "title":
            self._in_title = False
        if tag in {"h1", "h2", "h3"} and self._capture_heading == tag:
            text = re.sub(r"\s+", " ", "".join(getattr(self, "_heading_buf", [])).strip())
            if text:
                self.headings.append({"level": tag, "text": text[:120]})
            self._capture_heading = None
        if tag == "a" and self._link_href is not None:
            text = re.sub(r"\s+", " ", "".join(self._link_text).strip())
            self.links.append((self._link_href, text[:80]))
            self._link_href = None
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._in_script or self._in_style:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._capture_heading:
            self._heading_buf.append(data)
        if self._link_href is not None:
            self._link_text.append(data)
        # Collect short visible text for pattern signals only (later truncated)
        t = data.strip()
        if t and len(t) > 1:
            self._text_chunks.append(t)


def _guess_slug(label: str, path: str) -> str:
    blob = f"{label} {path}".strip()
    for rx, slug in _NAV_TO_SLUG:
        if rx.search(blob):
            return slug
    # path-based fallback
    seg = path.strip("/").split("/")[0] if path.strip("/") else ""
    if seg:
        for rx, slug in _NAV_TO_SLUG:
            if rx.search(seg):
                return slug
        return re.sub(r"[^a-z0-9_-]", "", seg.lower())[:32] or "page"
    return "page"


def _same_site(base: str, other: str) -> bool:
    try:
        a = urlparse(base)
        b = urlparse(other)
        return (a.netloc or "").lower() == (b.netloc or "").lower()
    except Exception:
        return False


def _should_skip_path(path: str) -> bool:
    low = (path or "").lower()
    return any(p in low for p in _SKIP_PATH_PARTS)


def _infer_section_pattern(headings: list[dict[str, str]], text_sample: str) -> dict[str, Any]:
    """Infer CMS-like section/item pattern from headings (structure only)."""
    h2 = [h["text"] for h in headings if h.get("level") == "h2"]
    h3 = [h["text"] for h in headings if h.get("level") == "h3"]
    h1 = [h["text"] for h in headings if h.get("level") == "h1"]

    # Point-like cards: several similar-length h2/h3 under a concept/service page
    point_candidates = h2[1:7] if len(h2) >= 3 else h3[:6]
    faq_q = [
        t
        for t in (h2 + h3)
        if t.endswith("？") or t.endswith("?") or t.startswith("Q") or "ですか" in t
    ]

    pattern = "intro_plus_points"
    if faq_q:
        pattern = "faq_qa"
    elif any("料金" in t or "メニュー" in t for t in h2 + h3):
        pattern = "menu_items"
    elif any("挨拶" in t or "代表" in t or "プロフィール" in t for t in h1 + h2):
        pattern = "greeting_profile"
    elif any("アクセス" in t or "住所" in t for t in h1 + h2):
        pattern = "access_details"

    return {
        "pattern": pattern,
        "h1": h1[:2],
        "section_headings": (h2 or h3)[:8],
        "suggested_point_count": min(max(len(point_candidates), 0), 8) or None,
        "suggested_faq_count": min(len(faq_q), 12) or None,
        "faq_question_headings": [q[:80] for q in faq_q[:8]],
        "point_title_hints": [p[:80] for p in point_candidates[:6]],
        # Tiny text fingerprint only — not usable as body copy
        "text_chars": len(text_sample),
    }


def _fetch_html(url: str, client: httpx.Client) -> str:
    resp = client.get(url, follow_redirects=True)
    resp.raise_for_status()
    raw = resp.content[:_MAX_BYTES]
    # Prefer charset from response; fallback utf-8
    return raw.decode(resp.encoding or "utf-8", errors="replace")


def analyze_page_html(url: str, html: str) -> dict[str, Any]:
    parser = _PageHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    parsed = urlparse(url)
    path = parsed.path or "/"
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()[:120]
    text_sample = " ".join(parser._text_chunks[:80])[:2000]
    pattern = _infer_section_pattern(parser.headings, text_sample)
    return {
        "url": url,
        "path": path,
        "title": title,
        "guess_slug": _guess_slug(title, path),
        "headings": parser.headings[:20],
        "structure": pattern,
        "outbound_links": parser.links[:80],
    }


def _discover_same_site_links(home_url: str, page: dict[str, Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for href, label in page.get("outbound_links") or []:
        abs_url = urljoin(home_url, href)
        if not _same_site(home_url, abs_url):
            continue
        path = urlparse(abs_url).path or "/"
        if _should_skip_path(path):
            continue
        # Prefer nav-like links (short labels)
        if label and len(label) > 40:
            continue
        # Drop anchors / query noise
        clean = abs_url.split("#")[0].split("?")[0]
        if clean.rstrip("/") == home_url.rstrip("/"):
            continue
        if clean in seen:
            continue
        seen.add(clean)
        found.append(clean)
    return found[:_MAX_PAGES]


def analyze_site(
    start_url: str,
    *,
    role: str = "reference",
    client: httpx.Client | None = None,
    max_pages: int = _MAX_PAGES,
) -> dict[str, Any]:
    """Crawl start URL + same-site nav links; return structure analysis."""
    start = _normalize_url(start_url)
    if not start:
        return {"ok": False, "role": role, "error": "empty_url", "pages": []}

    own_client = client is None
    client = client or httpx.Client(
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        follow_redirects=True,
    )
    pages: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        try:
            html = _fetch_html(start, client)
            home = analyze_page_html(start, html)
            home["guess_slug"] = "home"
            pages.append(home)
        except Exception as exc:
            return {
                "ok": False,
                "role": role,
                "start_url": start,
                "error": str(exc)[:200],
                "pages": [],
            }

        for link in _discover_same_site_links(start, home)[: max(0, max_pages - 1)]:
            try:
                html = _fetch_html(link, client)
                page = analyze_page_html(link, html)
                # Prefer path/label guess over title noise
                path = page.get("path") or "/"
                label = ""
                for href, text in home.get("outbound_links") or []:
                    if urljoin(start, href).split("#")[0].split("?")[0].rstrip("/") == link.rstrip("/"):
                        label = text
                        break
                page["nav_label"] = label
                page["guess_slug"] = _guess_slug(label or page.get("title") or "", path)
                pages.append(page)
            except Exception as exc:
                errors.append(f"{link}: {str(exc)[:80]}")
    finally:
        if own_client:
            client.close()

    nav = []
    for p in pages:
        nav.append(
            {
                "slug": p.get("guess_slug"),
                "label": p.get("nav_label") or p.get("title") or p.get("path"),
                "path": p.get("path"),
                "url": p.get("url"),
                "pattern": (p.get("structure") or {}).get("pattern"),
                "suggested_point_count": (p.get("structure") or {}).get("suggested_point_count"),
                "suggested_faq_count": (p.get("structure") or {}).get("suggested_faq_count"),
                "section_headings": (p.get("structure") or {}).get("section_headings") or [],
                "point_title_hints": (p.get("structure") or {}).get("point_title_hints") or [],
                "faq_question_headings": (p.get("structure") or {}).get("faq_question_headings") or [],
            }
        )

    return {
        "ok": True,
        "role": role,
        "start_url": start,
        "page_count": len(pages),
        "nav": nav,
        "pages": [
            {
                "url": p.get("url"),
                "path": p.get("path"),
                "title": p.get("title"),
                "guess_slug": p.get("guess_slug"),
                "nav_label": p.get("nav_label"),
                "structure": p.get("structure"),
                "headings": p.get("headings"),
            }
            for p in pages
        ],
        "errors": errors[:10],
        "policy": {
            "copy": "forbidden",
            "use": "structure_and_topic_headings_only",
            "facts_source": "hearing_sheet",
        },
    }


def analyze_hearing_live_sites(
    hearing: dict[str, Any],
    *,
    max_sites: int = 2,
    max_pages_per_site: int = _MAX_PAGES,
) -> dict[str, Any]:
    """Analyze top live URLs on a hearing. Safe no-op when disabled or no URLs."""
    if not live_site_analyze_enabled():
        return {"ok": False, "skipped": True, "reason": "disabled", "sites": []}

    # Type 1 usually has no existing site — still allow reference if present
    urls = collect_live_urls(hearing)
    if not urls:
        return {"ok": False, "skipped": True, "reason": "no_urls", "sites": []}

    # Prefer main_site / existing first
    def rank(item: dict[str, str]) -> int:
        role = item.get("role") or ""
        if role == "main_site":
            return 0
        if role == "existing":
            return 1
        if role.startswith("directive"):
            return 2
        return 3

    urls = sorted(urls, key=rank)[:max_sites]
    sites: list[dict[str, Any]] = []
    with httpx.Client(
        timeout=_TIMEOUT,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        follow_redirects=True,
    ) as client:
        for item in urls:
            sites.append(
                analyze_site(
                    item["url"],
                    role=item["role"],
                    client=client,
                    max_pages=max_pages_per_site,
                )
            )

    ok_sites = [s for s in sites if s.get("ok")]
    return {
        "ok": bool(ok_sites),
        "skipped": False,
        "site_count": len(ok_sites),
        "sites": sites,
        "nav_union": _merge_nav(ok_sites),
        "policy": {
            "copy": "forbidden",
            "use": "structure_and_topic_headings_only",
            "facts_source": "hearing_sheet",
        },
    }


def _merge_nav(sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_slug: dict[str, dict[str, Any]] = {}
    for site in sites:
        for row in site.get("nav") or []:
            if not isinstance(row, dict):
                continue
            slug = _s(row.get("slug"))
            if not slug:
                continue
            prev = by_slug.get(slug)
            if not prev:
                by_slug[slug] = dict(row)
                continue
            # Prefer richer heading hints
            if len(row.get("section_headings") or []) > len(prev.get("section_headings") or []):
                by_slug[slug] = dict(row)
    order = ["home", "concept", "service", "faq", "greeting", "staff", "reviews", "access", "contact", "recruit"]
    out: list[dict[str, Any]] = []
    for slug in order:
        if slug in by_slug:
            out.append(by_slug.pop(slug))
    out.extend(by_slug.values())
    return out


def enrich_hearing_with_live_site(
    hearing: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Attach live_site_analysis onto hearing (in place). Idempotent unless force."""
    if not isinstance(hearing, dict):
        return hearing
    if hearing.get("live_site_analysis") and not force:
        return hearing
    try:
        hearing["live_site_analysis"] = analyze_hearing_live_sites(hearing)
    except Exception as exc:
        hearing["live_site_analysis"] = {
            "ok": False,
            "error": str(exc)[:200],
            "sites": [],
            "nav_union": [],
        }
    return hearing


def live_structure_for_page(hearing: dict[str, Any], page: dict[str, Any]) -> dict[str, Any] | None:
    """Return matching live nav/structure row for a blueprint page, if any."""
    analysis = hearing.get("live_site_analysis") if isinstance(hearing.get("live_site_analysis"), dict) else {}
    nav = analysis.get("nav_union") or []
    if not nav:
        return None
    slug = _s(page.get("slug"))
    ptype = _s(page.get("type"))
    label = _s(page.get("nav_label"))
    for row in nav:
        if not isinstance(row, dict):
            continue
        if slug and row.get("slug") == slug:
            return row
    # type-based
    type_map = {
        "コンセプト": "concept",
        "サービス": "service",
        "よくある質問": "faq",
        "スタッフ (代表挨拶・代表のみ)": "greeting",
        "お客様の声": "reviews",
        "access": "access",
        "contact": "contact",
        "top_satellite": "home",
        "top": "home",
    }
    want = type_map.get(ptype)
    if want:
        for row in nav:
            if isinstance(row, dict) and row.get("slug") == want:
                return row
    if label:
        guess = _guess_slug(label, "")
        for row in nav:
            if isinstance(row, dict) and row.get("slug") == guess:
                return row
    return None


def structure_hint_lines(hearing: dict[str, Any], page: dict[str, Any]) -> list[str]:
    """English/Japanese prompt lines for AI-1/AI-2 — structure only, no body copy."""
    row = live_structure_for_page(hearing, page)
    if not row:
        return []
    lines = [
        "LIVE SITE STRUCTURE HINT (reference only — do NOT copy sentences from the live site):",
        f"- matched live page: {row.get('label') or row.get('path')} ({row.get('url')})",
        f"- pattern: {row.get('pattern')}",
    ]
    if row.get("suggested_point_count"):
        lines.append(f"- suggested item/point count: {row['suggested_point_count']}")
    if row.get("suggested_faq_count"):
        lines.append(f"- suggested FAQ count: {row['suggested_faq_count']}")
    heads = row.get("section_headings") or []
    if heads:
        lines.append("- live section headings (topics only): " + " / ".join(str(h)[:40] for h in heads[:6]))
    points = row.get("point_title_hints") or []
    if points:
        lines.append("- live point title hints (rewrite from hearing facts, do not paste): " + " / ".join(str(p)[:40] for p in points[:5]))
    faqs = row.get("faq_question_headings") or []
    if faqs:
        lines.append(
            "- live FAQ question topics (answer ONLY from hearing facts; if hearing has no Q&A leave empty): "
            + " / ".join(str(q)[:40] for q in faqs[:5])
        )
    lines.append("- Hearing sheet facts always win. Empty hearing facts → empty output.")
    return lines


def apply_live_structure_to_page_sections(page: dict[str, Any], hearing: dict[str, Any]) -> None:
    """Optionally bump point/service/faq item counts to match live structure (in place)."""
    row = live_structure_for_page(hearing, page)
    if not row or not isinstance(page, dict):
        return
    page["live_structure"] = {
        "url": row.get("url"),
        "pattern": row.get("pattern"),
        "suggested_point_count": row.get("suggested_point_count"),
        "suggested_faq_count": row.get("suggested_faq_count"),
        "section_headings": row.get("section_headings") or [],
        "point_title_hints": row.get("point_title_hints") or [],
        "faq_question_headings": row.get("faq_question_headings") or [],
    }
    # Attach topic hints into content_seeds when hearing seeds are thin (not full copy)
    seeds = [str(s).strip() for s in (page.get("content_seeds") or []) if str(s).strip()]
    ptype = str(page.get("type") or "")
    slug = str(page.get("slug") or "")
    if (slug == "concept" or "コンセプト" in ptype) and len(seeds) < 2:
        hints = [str(h).strip() for h in (row.get("point_title_hints") or []) if str(h).strip()]
        if hints:
            # Mark as structure topic hints — AI-2 must still ground in hearing
            page["live_topic_hints"] = hints[:6]
    if (slug == "faq" or "質問" in ptype) and not seeds:
        faqs = [str(q).strip() for q in (row.get("faq_question_headings") or []) if str(q).strip()]
        if faqs:
            page["live_topic_hints"] = faqs[:8]
            # Do NOT auto-fill FAQ answers — only expose question topics as hints
