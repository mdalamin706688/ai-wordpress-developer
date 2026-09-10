"""V2 Type 4 (サテライトリニューアル) hearing parser + blueprint tests."""

from pathlib import Path

from ai_agent.v2.blueprint import (
    TYPE4_BLUEPRINT_VERSION,
    build_site_blueprint,
    finalize_type4_blueprint,
    inject_missing_type3_nav_pages,
    is_v2_lab_type,
)
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.production_types import ProductionType
from ai_agent.v2.prompt_rules import format_v2_page_rules
from ai_agent.v2.section_rules import dynamic_section_rule

SAMPLE = Path(__file__).resolve().parents[1] / "demo" / "v2" / "samples" / "type4-satellite-renewal.csv"


def test_parse_type4_satellite_renewal_csv():
    hearing = parse_hearing_sheet(SAMPLE.read_text(encoding="utf-8-sig"))
    assert hearing["production_type"] == ProductionType.TYPE4_SATELLITE_RENEWAL.value
    assert hearing["production_label"] == "サテライトリニューアル"
    assert is_v2_lab_type(hearing)
    project = hearing.get("project") or {}
    assert "peraichi.com" in str(project.get("existing_url") or "")
    assert project.get("domain") == "dansharikoubou.com"
    assert "参考にしない" in str(project.get("existing_site_copy") or "")
    assert "踏襲しない" in str(hearing.get("top_inherit_note") or "")
    assert len(hearing["pages"]) == 6
    assert len(hearing["existing_pages"]) == 0
    assert len(hearing["focus_keywords"]) == 5
    assert len(hearing["seo_pages"]) == 15
    assert len(hearing["tag_pages"]) == 10


def test_type4_blueprint_satellite_plus_renewal():
    hearing = parse_hearing_sheet(SAMPLE.read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    assert bp["production_type"] == ProductionType.TYPE4_SATELLITE_RENEWAL.value
    assert bp["clone_mode"] == "bbs_satellite_renewal"
    assert bp["pages"][0]["type"] == "top_satellite"
    assert "peraichi.com" in str(bp["pages"][0].get("existing_url") or "")
    seeds = bp["pages"][0].get("content_seeds") or []
    for kw in hearing["focus_keywords"]:
        assert kw in seeds
    slugs = [p["slug"] for p in bp["pages"]]
    assert slugs[0] == "home"
    for required in ("access", "blog", "reviews", "contact", "sitemap", "privacy", "column"):
        assert required in slugs
    assert "reason" in slugs or "concept" in slugs
    assert "service" in slugs
    sat = bp["satellite"]
    assert sat["domain"] == "dansharikoubou.com"
    assert sat["main_site_urls"]
    ren = bp["renewal"]
    assert "peraichi.com" in str(ren.get("existing_url") or "")
    assert "参考にしない" in str(ren.get("existing_site_copy") or "")
    assert bp["stats"]["seo_pages"] == 15
    assert bp["stats"]["tag_pages"] == 10
    assert bp["stats"]["nav_pages"] >= 12
    assert bp.get("blueprint_version") == TYPE4_BLUEPRINT_VERSION
    assert bp["ai_stages"]["planner"] == "complete"
    assert "warnings" not in bp


def test_type4_inject_and_finalize():
    hearing = parse_hearing_sheet(SAMPLE.read_text(encoding="utf-8-sig"))
    partial = build_site_blueprint(hearing)
    # Simulate truncated older payload
    partial["pages"] = list(partial["pages"] or [])[:3]
    assert inject_missing_type3_nav_pages(partial, hearing) is True or len(partial["pages"]) >= 3
    final = finalize_type4_blueprint(partial, hearing)
    assert final["production_type"] == ProductionType.TYPE4_SATELLITE_RENEWAL.value
    assert final.get("blueprint_version") == TYPE4_BLUEPRINT_VERSION
    assert len(final.get("pages") or []) >= 12
    assert final.get("renewal")
    assert final.get("satellite")


def test_type4_renewal_prompt_rules():
    hearing = parse_hearing_sheet(SAMPLE.read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    home = bp["pages"][0]
    rules = format_v2_page_rules(home, hearing)
    assert "既存サイト文言は参考にしない" in rules
    assert "踏襲しない" in rules or "TOP方針" in rules
    assert "peraichi.com" in rules

    section = (home.get("sections") or [{}])[0]
    dyn = dynamic_section_rule(section, home, hearing)
    assert "参考にしない" in dyn or "既存サイト文言" in dyn
    assert "peraichi.com" in dyn
