"""Nested content-block schema across ALL page types (concept was only an example)."""

from __future__ import annotations

from pathlib import Path

from ai_agent.v2.blueprint import build_site_blueprint
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.page_catalog import nested_fields_for_section, sections_for_page_type
from ai_agent.v2.prompt_rules import json_example_for_page
from ai_agent.v2.writer import parse_v2_sections_json, _section_value_as_text

SAMPLES = Path(__file__).resolve().parents[1] / "demo" / "v2" / "samples"


def _ids(page: dict) -> list[str]:
    return [str(s["id"]) for s in (page.get("sections") or []) if isinstance(s, dict)]


def test_all_nav_content_pages_use_nested_blocks():
    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    by_slug = {p["slug"]: p for p in bp["pages"]}

    # Concept
    concept = by_slug["concept"]
    assert "concept_catchphrase" in _ids(concept)
    assert "point_1" in _ids(concept)
    assert nested_fields_for_section(next(s for s in concept["sections"] if s["id"] == "point_1")) == [
        "title",
        "description",
    ]

    # Service
    service = by_slug["service"]
    assert "service_intro" in _ids(service)
    assert "service_1" in _ids(service)
    assert "service_list" not in _ids(service)

    # FAQ
    faq = by_slug["faq"]
    assert "faq_intro" in _ids(faq)
    assert nested_fields_for_section(next(s for s in faq["sections"] if s["id"] == "faq_intro")) == [
        "heading",
        "lead",
    ]

    # Greeting
    greeting = by_slug["greeting"]
    assert "greeting_intro" in _ids(greeting)
    assert "greeting_profile" in _ids(greeting)
    assert nested_fields_for_section(
        next(s for s in greeting["sections"] if s["id"] == "greeting_profile")
    ) == ["name", "role", "message", "career"]

    # TOP
    home = by_slug["home"]
    assert "top_catchphrase" in _ids(home)
    assert "lead" in _ids(home)
    assert "business_info" in _ids(home)
    assert "cta" in _ids(home)
    assert "hero_brand_name" not in _ids(home)
    assert nested_fields_for_section(next(s for s in home["sections"] if s["id"] == "top_catchphrase")) == [
        "brand_name",
        "catchphrase",
        "short_description",
    ]

    # Access / contact
    assert "access_details" in _ids(by_slug["access"])
    assert "contact_details" in _ids(by_slug["contact"])

    # Reviews
    reviews = by_slug["reviews"]
    assert "reviews_intro" in _ids(reviews)
    assert "cta" in _ids(reviews)


def test_seo_and_tag_use_nested_points():
    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    seo = (bp.get("seo_pages") or [None])[0]
    assert seo is not None
    ids = _ids(seo)
    assert "seo_intro" in ids
    assert "seo_point_1" in ids
    assert "seo_summary" in ids
    assert "intro_heading" not in ids
    tag = (bp.get("tag_pages") or [None])[0]
    assert tag is not None
    assert "tag_intro" in _ids(tag)
    assert "tag_point_1" in _ids(tag)


def test_json_example_emits_nested_objects_for_multiple_pages():
    for ptype, seeds in (
        ("コンセプト", ["a", "b", "c"]),
        ("サービス", ["外壁", "屋根"]),
        ("access", []),
        ("seo", []),
    ):
        page = {"sections": sections_for_page_type(ptype, content_seeds=seeds)}
        example = json_example_for_page(page)
        assert "{" in example
        assert "sections" in example


def test_parse_v2_keeps_nested_objects():
    raw = (
        '{"sections":{'
        '"top_catchphrase":{"brand_name":"太陽塗装","catchphrase":"調和","short_description":"心身"},'
        '"business_info":{"name":"太陽塗装","postal":"000-0000","address":"","phone":"","hours":"",'
        '"closed":"","payment":"","email":"","instagram":""},'
        '"point_1":{"title":"脳と心","description":"育てる"}'
        "}}"
    )
    sections = parse_v2_sections_json(raw)
    assert sections["top_catchphrase"]["brand_name"] == "太陽塗装"
    assert sections["point_1"]["title"] == "脳と心"
    assert sections["business_info"]["name"] == "太陽塗装"
    text = _section_value_as_text(sections["top_catchphrase"])
    assert '"catchphrase"' in text
