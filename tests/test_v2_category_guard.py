"""Category playbooks + post-write guards."""

from __future__ import annotations

from ai_agent.v2.category_guard import (
    apply_category_guards,
    category_playbook_lines,
    scrub_page_sections,
    validate_page_sections,
)
from ai_agent.v2.prompt_rules import format_v2_page_rules
from ai_agent.v2.site_category import derive_site_category


def test_playbooks_differ_by_category():
    lead = "\n".join(category_playbook_lines("lead_gen"))
    recruit = "\n".join(category_playbook_lines("recruit"))
    assert "PLAYBOOK" in lead and "PLAYBOOK" in recruit
    assert "job seekers" in recruit.lower() or "求職" in recruit or "job" in recruit.lower()
    assert "customers" in lead.lower() or "集客" in lead or "inquiry" in lead.lower()
    assert lead != recruit


def test_scrub_strips_ranking_and_coerces_fields():
    hearing = {
        "project": {"purpose": "集客", "production_kind": "通常"},
        "flags": {},
        "pages": [],
    }
    page = {
        "slug": "home",
        "type": "top_satellite",
        "sections": [
            {"id": "selling_point_1", "mode": "expand"},
            {"id": "seo_point_1", "mode": "generate"},
        ],
    }
    sections = {
        "selling_point_1": {"title": "地域1番店", "description": "安心施工"},
        "seo_point_1": {"title": "A", "body": "本文"},
    }
    cleaned, applied, remaining = apply_category_guards(sections, page, hearing)
    assert "地域1番店" not in str(cleaned.get("selling_point_1"))
    assert cleaned["seo_point_1"].get("description") == "本文"
    assert "body" not in cleaned["seo_point_1"]
    assert any("ranking" in a or "coerced" in a for a in applied)
    assert not any(i.startswith("invented_ranking") for i in remaining)


def test_scrub_fills_faq_intro():
    hearing = {"project": {"purpose": "集客", "production_kind": "通常"}, "flags": {}, "pages": []}
    page = {
        "slug": "faq",
        "type": "よくある質問",
        "sections": [{"id": "faq_intro", "mode": "generate"}, {"id": "faq_items", "mode": "blank"}],
    }
    sections = {"faq_intro": {"heading": "", "lead": ""}, "faq_items": ""}
    cleaned, applied, _ = apply_category_guards(sections, page, hearing)
    assert cleaned["faq_intro"].get("heading") == "よくあるご質問"
    assert "filled_faq_intro_heading" in applied


def test_scrub_strips_recruit_copy_on_lead_gen():
    hearing = {"project": {"purpose": "集客", "production_kind": "通常"}, "flags": {}, "pages": []}
    page = {
        "slug": "home",
        "type": "top_satellite",
        "sections": [{"id": "lead", "mode": "expand"}],
    }
    sections = {"lead": {"heading": "塗装", "body": "求人応募はこちら。履歴書をご送付ください。"}}
    cleaned, applied, remaining = apply_category_guards(sections, page, hearing)
    body = str(cleaned["lead"].get("body") or "")
    assert "求人応募" not in body
    assert "履歴書" not in body
    assert any("recruit" in a for a in applied)


def test_page_rules_include_playbook():
    hearing = {
        "production_type": "type3",
        "project": {
            "purpose": "集客 (訪問型)",
            "production_kind": "通常",
            "domain": "taiyotoso.jp",
            "site_category": "lead_gen",
            "site_brief": derive_site_category(
                {"project": {"purpose": "集客", "production_kind": "通常"}, "flags": {}, "pages": []}
            ),
        },
        "flags": {},
        "pages": [],
    }
    rules = format_v2_page_rules(
        {"nav_label": "TOP", "type": "top_satellite", "slug": "home", "sections": []},
        hearing,
    )
    assert "SITE BRIEF" in rules
    assert "PLAYBOOK" in rules
    assert "lead_gen" in rules


def test_validate_detects_ranking_before_scrub():
    hearing = {"project": {"purpose": "集客"}, "flags": {}, "pages": []}
    page = {"slug": "home", "type": "top_satellite", "sections": [{"id": "selling_point_1"}]}
    sections = {"selling_point_1": {"title": "地域1番店です", "description": "x"}}
    issues = validate_page_sections(sections, page, hearing)
    assert any(i.startswith("invented_ranking") for i in issues)
    cleaned, _ = scrub_page_sections(sections, page, hearing)
    issues2 = validate_page_sections(cleaned, page, hearing)
    assert not any(i.startswith("invented_ranking") for i in issues2)
