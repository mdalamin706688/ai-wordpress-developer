"""V2 Type 1 (新規) hearing parser + blueprint tests."""

from pathlib import Path

from ai_agent.v2.blueprint import (
    TYPE1_BLUEPRINT_VERSION,
    build_site_blueprint,
    finalize_type1_blueprint,
    inject_missing_type3_nav_pages,
    is_v2_lab_type,
)
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.production_types import ProductionType

SAMPLE = Path(__file__).resolve().parents[1] / "demo" / "v2" / "samples" / "type1-shinki.csv"


def test_parse_type1_shinki_csv():
    hearing = parse_hearing_sheet(SAMPLE.read_text(encoding="utf-8-sig"))
    assert hearing["production_type"] == ProductionType.TYPE1_SHINKI.value
    assert hearing["production_label"] == "新規"
    assert is_v2_lab_type(hearing)
    project = hearing.get("project") or {}
    assert project.get("domain") == "sand-palce.com"
    assert not str(project.get("existing_url") or "").strip()
    assert len(hearing["pages"]) == 7
    assert len(hearing["existing_pages"]) == 0
    assert len(hearing["focus_keywords"]) == 5
    assert len(hearing["seo_pages"]) == 15
    assert len(hearing["tag_pages"]) == 10


def test_type1_blueprint_standard_template():
    hearing = parse_hearing_sheet(SAMPLE.read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    assert bp["production_type"] == ProductionType.TYPE1_SHINKI.value
    assert bp["clone_mode"] == "bbs_standard_template"
    assert bp["pages"][0]["type"] == "top"
    assert bp["pages"][0]["type"] != "top_satellite"
    slugs = [p["slug"] for p in bp["pages"]]
    assert slugs[0] == "home"
    assert "concept" in slugs
    assert "service" in slugs
    assert "faq" in slugs
    # Empty menu/料金 may be omitted from nav when hearing marks leave_blank.
    if "menu" not in slugs:
        omitted = bp.get("omitted_pages") or []
        assert any(str(r.get("slug")) == "menu" for r in omitted if isinstance(r, dict))
    for required in ("access", "blog", "contact", "sitemap", "privacy", "column"):
        assert required in slugs
    # page composition ② — reviews only when 口コミ slots filled (type1 sample has none)
    assert "reviews" not in slugs
    # page composition ② — AI blog when AIサポート=あり
    assert "ai-blog" in slugs
    assert hearing["flags"].get("include_ai_blog") is True
    shinki = bp["shinki"]
    assert shinki["domain"] == "sand-palce.com"
    assert bp["stats"]["seo_pages"] == 15
    assert bp["stats"]["tag_pages"] == 10
    assert bp["stats"]["nav_pages"] >= 12
    assert bp.get("blueprint_version") == TYPE1_BLUEPRINT_VERSION
    assert bp["ai_stages"]["planner"] == "complete"
    assert "warnings" not in bp
    assert not bp.get("renewal")


def test_type1_inject_and_finalize():
    hearing = parse_hearing_sheet(SAMPLE.read_text(encoding="utf-8-sig"))
    partial = build_site_blueprint(hearing)
    partial["pages"] = list(partial["pages"] or [])[:3]
    inject_missing_type3_nav_pages(partial, hearing)
    final = finalize_type1_blueprint(partial, hearing)
    assert final["production_type"] == ProductionType.TYPE1_SHINKI.value
    assert final.get("blueprint_version") == TYPE1_BLUEPRINT_VERSION
    assert len(final.get("pages") or []) >= 12
    assert final.get("shinki")
    assert final["clone_mode"] == "bbs_standard_template"
