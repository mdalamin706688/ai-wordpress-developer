"""Advanced prompt header-page section tabs (static gnav only)."""

from __future__ import annotations

from ai_agent.pipeline.copy_generator import build_demo_user_prompt
from ai_agent.pipeline.prompt_rules import (
    HEADER_PAGES,
    SERVICE_SECTION_ITEMS,
    TOP_SECTION_ITEMS,
    page_prompt_rules,
    prompt_sections_catalog,
)
from ai_agent.pipeline.site_composer import compose_site_draft


def test_prompt_sections_catalog_has_all_header_tabs():
    catalog = prompt_sections_catalog()
    ids = [t["id"] for t in catalog["tabs"]]
    assert ids == [p["id"] for p in HEADER_PAGES]
    assert "top" in ids and "service" in ids and "concept" in ids
    assert "blog" in ids and "column" in ids
    top = next(t for t in catalog["tabs"] if t["id"] == "top")
    service = next(t for t in catalog["tabs"] if t["id"] == "service")
    assert [i["id"] for i in top["items"]] == [i["id"] for i in TOP_SECTION_ITEMS]
    assert [i["id"] for i in service["items"]] == [i["id"] for i in SERVICE_SECTION_ITEMS]
    blog = next(t for t in catalog["tabs"] if t["id"] == "blog")
    assert blog.get("shell") is True


def test_page_prompt_rules_list_web_items():
    top = page_prompt_rules("top")
    assert "Hero" in top or "hero" in top
    assert "Access" in top or "アクセス" in top
    assert "body_paragraphs" in top
    svc = page_prompt_rules("service")
    assert "Service blocks" in svc or "services" in svc
    concept = page_prompt_rules("concept")
    assert "コンセプト" in concept or "Concept" in concept
    feature = page_prompt_rules("feature")
    assert "下層" in feature or "feature" in feature.lower()


def test_demo_prompt_injects_active_page_rules():
    hearing = {"business_name": "緑の間", "menu": [{"name": "アロマ", "duration": "60分", "price": "¥8,800"}]}
    top_prompt = build_demo_user_prompt(hearing, page="top")
    assert "ページ: top" in top_prompt or "ページ: TOP" in top_prompt
    assert "必ず6要素" in top_prompt
    assert "Access" in top_prompt or "アクセス" in top_prompt
    svc_prompt = build_demo_user_prompt(hearing, page="service")
    assert "ページ: SERVICE" in svc_prompt or "ページ: service" in svc_prompt


def test_classic_lab_template_unchanged():
    from ai_agent.pipeline.prompt_rules import default_lab_user_template

    tpl = default_lab_user_template()
    assert "{hearing}" in tpl
    assert "必ず6要素" in tpl
    assert "{page_rules}" not in tpl
    assert "--- TOP RULES ---" not in tpl


def test_compose_has_all_header_pages():
    hearing = {
        "business_name": "緑の間",
        "station": "桜新町駅 徒歩4分",
        "phone": "03-1234-5678",
        "concept": "日常の疲れをほどく空間。",
        "catchcopy": "近所で整える、くつろぎ時間",
        "menu": [{"name": "アロマ", "duration": "60分", "price": "¥8,800"}],
        "missing": ["スタッフ紹介"],
    }
    site = compose_site_draft(hearing, {"cta": "ご予約はこちら", "body_paragraphs": ["a"] * 6})
    ids = [p["id"] for p in site["pages"]]
    for need in (
        "home",
        "concept",
        "service",
        "greeting",
        "menu",
        "faq",
        "feature",
        "access",
        "blog",
        "column",
        "reviews",
        "contact",
    ):
        assert need in ids
    assert site["sections"]["top"]["menu"]["items"][0]["price"] == "¥8,800"
    assert site["sections"]["service"]["services"][0]["heading"] == "アロマ"
    assert site["sections"]["blog"]["shell"] is True
    assert site["published"] is False
