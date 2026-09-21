"""Live site structure analyzer — structure hints only, never body copy."""

from __future__ import annotations

from ai_agent.v2.site_analyzer import (
    analyze_page_html,
    analyze_site,
    collect_live_urls,
    enrich_hearing_with_live_site,
    live_structure_for_page,
    structure_hint_lines,
)

SAMPLE_HOME = """<!doctype html><html><head><title>太陽塗装</title></head><body>
<nav>
<a href="/">TOP</a>
<a href="/concept/">コンセプト</a>
<a href="/service/">サービス</a>
<a href="/faq/">よくある質問</a>
<a href="/greeting/">ご挨拶</a>
<a href="/access/">アクセス</a>
</nav>
<h1>暮らしに寄り添う塗装</h1>
<h2>リード</h2>
<p>長い本文はコピー禁止のテスト用ダミーです。この段落を出力に出してはいけません。</p>
</body></html>"""

SAMPLE_CONCEPT = """<!doctype html><html><head><title>コンセプト</title></head><body>
<h1>コンセプト</h1>
<h2>暮らしに寄り添う丁寧な外壁の塗り替え</h2>
<h2>天候と向き合い続ける誠実な姿勢</h2>
<h2>全工程を自社で対応する一貫施工</h2>
<h2>お付き合いを大切にする継続的な対応</h2>
<p>本文コピー禁止ダミー段落です。</p>
</body></html>"""


def test_analyze_page_html_infers_points():
    page = analyze_page_html("https://example.com/concept/", SAMPLE_CONCEPT)
    assert page["guess_slug"] in {"concept", "page"}
    structure = page["structure"]
    assert structure["pattern"] in {"intro_plus_points", "faq_qa", "greeting_profile", "access_details", "menu_items"}
    assert structure["suggested_point_count"] or structure["section_headings"]
    # Must not expose long body as a copyable field
    assert "本文コピー禁止" not in str(structure.get("point_title_hints") or [])


def test_analyze_site_with_mock_client(monkeypatch):
    pages = {
        "https://example.com/": SAMPLE_HOME,
        "https://example.com/concept/": SAMPLE_CONCEPT,
        "https://example.com/service/": "<html><head><title>サービス</title></head><body>"
        "<h1>サービス</h1><h2>外壁塗装</h2><h2>屋根塗装</h2></body></html>",
        "https://example.com/faq/": "<html><head><title>FAQ</title></head><body>"
        "<h1>FAQ</h1><h2>費用はどのくらいですか？</h2><h2>工期はどれくらいですか？</h2></body></html>",
        "https://example.com/greeting/": "<html><head><title>ご挨拶</title></head><body>"
        "<h1>代表挨拶</h1><h2>プロフィール</h2></body></html>",
        "https://example.com/access/": "<html><head><title>アクセス</title></head><body>"
        "<h1>アクセス</h1><h2>住所</h2></body></html>",
    }

    class FakeResp:
        def __init__(self, url: str):
            self.url = url
            self.content = pages[url].encode("utf-8")
            self.encoding = "utf-8"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def get(self, url, follow_redirects=True):
            # normalize trailing slash variants
            key = url if url in pages else url.rstrip("/") + "/"
            if key not in pages:
                raise RuntimeError(f"unexpected url {url}")
            return FakeResp(key)

        def close(self) -> None:
            return None

    monkeypatch.setattr("ai_agent.v2.site_analyzer.httpx.Client", FakeClient)
    result = analyze_site("https://example.com/", role="main_site", client=FakeClient())
    assert result["ok"] is True
    assert result["page_count"] >= 2
    slugs = {row["slug"] for row in result["nav"]}
    assert "home" in slugs
    assert "concept" in slugs or "service" in slugs or "faq" in slugs
    assert result["policy"]["copy"] == "forbidden"


def test_collect_and_enrich_hearing_uses_analysis(monkeypatch):
    hearing = {
        "production_type": "type3",
        "project": {"business_name": "テスト塗装", "existing_url": ""},
        "reference_sites": [{"kind": "参考サイト (お客様所有)", "url": "https://example.com/"}],
        "pages": [],
        "page_directives": {},
    }
    assert collect_live_urls(hearing)

    class FakeResp:
        def __init__(self):
            self.content = SAMPLE_HOME.encode("utf-8")
            self.encoding = "utf-8"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, follow_redirects=True):
            return FakeResp()

        def close(self) -> None:
            return None

    monkeypatch.setenv("BBS_LIVE_SITE_ANALYZE", "1")
    monkeypatch.setattr("ai_agent.v2.site_analyzer.httpx.Client", FakeClient)
    enrich_hearing_with_live_site(hearing, force=True)
    assert hearing["live_site_analysis"]["ok"] is True
    page = {"slug": "concept", "type": "コンセプト", "nav_label": "コンセプト"}
    # home-only crawl still returns nav hints; concept may be unmatched — that's ok
    hints = structure_hint_lines(hearing, {"slug": "home", "type": "top_satellite"})
    assert any("LIVE SITE STRUCTURE" in h for h in hints)
    assert any("do NOT copy" in h or "コピー" in h or "copy" in h.lower() for h in hints)
    row = live_structure_for_page(hearing, {"slug": "home", "type": "top_satellite"})
    assert row is not None
