"""Type 3 site category from hearing purpose/kind (dynamic, not fixed industry)."""

from __future__ import annotations

from ai_agent.v2.prompt_packs import default_ai2_system_for_type
from ai_agent.v2.prompt_rules import format_v2_page_rules
from ai_agent.v2.site_category import derive_site_category, site_brief_lines
from ai_agent.v2.writer import coerce_page_section_text


def test_lead_gen_category_from_purpose():
    hearing = {
        "project": {
            "purpose": "集客 (訪問型)",
            "production_kind": "通常",
            "domain": "taiyotoso.jp",
            "business_name": "有限会社太陽塗装",
        },
        "flags": {},
        "pages": [{"type": "サービス", "items": ["外壁塗装"]}],
    }
    brief = derive_site_category(hearing)
    assert brief["category"] == "lead_gen"
    assert brief["audience"] == "customers"
    assert "集客" in brief["purpose"]


def test_recruit_category_from_kind():
    hearing = {
        "project": {"purpose": "", "production_kind": "リクルート", "domain": "example.jp"},
        "flags": {"include_recruit": True},
        "recruit": {"enabled": True, "production_kind": "リクルート"},
        "pages": [{"type": "リクルート (総合)", "items": ["塗装スタッフ"]}],
    }
    brief = derive_site_category(hearing)
    assert brief["category"] == "recruit"
    assert brief["audience"] == "job_seekers"


def test_site_brief_in_page_rules():
    hearing = {
        "production_type": "type3",
        "project": {
            "purpose": "集客 (訪問型)",
            "production_kind": "通常",
            "domain": "taiyotoso.jp",
            "site_category": "lead_gen",
            "site_brief": derive_site_category(
                {
                    "project": {
                        "purpose": "集客 (訪問型)",
                        "production_kind": "通常",
                        "domain": "taiyotoso.jp",
                    },
                    "flags": {},
                    "pages": [],
                }
            ),
        },
        "flags": {},
        "pages": [],
    }
    page = {"nav_label": "TOP", "type": "top_satellite", "slug": "home", "sections": []}
    rules = format_v2_page_rules(page, hearing)
    assert "SITE BRIEF" in rules
    assert "lead_gen" in rules
    assert "集客" in rules


def test_ai2_prompt_mentions_purpose_driven_category():
    text = default_ai2_system_for_type("type3")
    assert "サイト制作目的" in text or "SITE BRIEF" in text or "lead_gen" in text
    assert "branch landing site" not in text
    assert "地域1番" in text or "rankings" in text.lower()


def test_coerce_body_to_description_for_seo_point():
    page = {
        "sections": [
            {"id": "seo_point_1", "mode": "generate"},
            {"id": "seo_intro", "mode": "generate"},
        ]
    }
    text = {
        "seo_point_1": {"title": "A", "body": "本文です"},
        "seo_intro": {"heading": "H", "body": "B"},
    }
    out = coerce_page_section_text(page, text)
    assert out["seo_point_1"] == {"title": "A", "description": "本文です"}
    assert "body" not in out["seo_point_1"]
    assert out["seo_intro"]["body"] == "B"


def test_brief_lines_differ_recruit_vs_lead():
    lead = "\n".join(
        site_brief_lines(
            {"project": {"purpose": "集客", "production_kind": "通常"}, "flags": {}, "pages": []}
        )
    )
    recruit = "\n".join(
        site_brief_lines(
            {
                "project": {"purpose": "", "production_kind": "リクルート"},
                "flags": {"include_recruit": True},
                "pages": [],
            }
        )
    )
    assert "lead_gen" in lead
    assert "recruit" in recruit
    assert lead != recruit
