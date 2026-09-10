"""V2 Type 2 (リニューアル / Renewal) hearing parser + blueprint tests."""

from pathlib import Path

from ai_agent.v2.blueprint import build_site_blueprint, finalize_type2_blueprint, is_v2_lab_type
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.production_types import ProductionType
from ai_agent.v2.writer import pages_to_write

SAMPLE = Path(__file__).resolve().parents[1] / "demo" / "v2" / "samples" / "type2-renewal.csv"


def test_parse_type2_renewal_csv():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    assert hearing["production_type"] == ProductionType.TYPE2_RENEWAL.value
    assert hearing["production_label"] == "リニューアル"
    assert hearing["project"]["business_name"] == "Volts Electrical Works"
    assert hearing["project"]["existing_url"] == "https://voltsdenkikouji.com/"
    assert hearing["project"]["existing_site_colors"]
    assert len(hearing["pages"]) == 4
    assert len(hearing["existing_pages"]) == 9
    assert all(p.get("required") == "必要" for p in hearing["existing_pages"])
    assert hearing["form_pages"]
    assert hearing["sitemap"].get("url")
    assert hearing["privacy"].get("url")
    assert len(hearing["seo_pages"]) == 15
    assert len(hearing["tag_keywords"]) == 10
    assert is_v2_lab_type(hearing)


def test_type2_blueprint_from_existing_pages():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    assert bp["production_type"] == ProductionType.TYPE2_RENEWAL.value
    assert bp["clone_mode"] == "existing_client_site"
    assert "warnings" not in bp
    assert bp["pages"][0]["type"] == "top"
    assert bp["pages"][0]["existing_url"] == "https://voltsdenkikouji.com/"
    slugs = [p["slug"] for p in bp["pages"]]
    assert "home" in slugs
    assert "service" in slugs
    assert "air-conditioner" in slugs
    assert "about" in slugs
    assert "works" in slugs
    assert "estimates" in slugs
    assert "sitemap" in slugs
    assert "privacy" in slugs
    # Empty メニュー may be omitted (same leave_blank rule as satellite).
    if hearing.get("page_directives", {}).get("menu", {}).get("leave_blank"):
        assert "menu" not in slugs
        assert any(str(r.get("slug")) == "menu" for r in (bp.get("omitted_pages") or []))
    else:
        assert "menu" in slugs
    assert "estimates" in slugs
    assert "contact" in slugs  # フォームURL1 お問合わせ is 必要 (separate from estimates)
    assert "access" not in slugs  # アクセスページはありますか=いいえ
    assert "company" in slugs  # 備考: アクセス→会社概要 (directory=company)
    company = next(p for p in bp["pages"] if p["slug"] == "company")
    assert company["nav_label"] == "会社概要"
    assert any("電気walker" in str(s) or "denki-walker" in str(s) for s in (company.get("content_seeds") or []))
    assert hearing["flags"]["top_inherit"] is False
    assert "踏襲しない" in str(hearing.get("top_inherit_note") or "")
    home = next(p for p in bp["pages"] if p["slug"] == "home")
    home_rules = " ".join(str(s.get("rule") or "") for s in (home.get("sections") or []))
    assert "参考にしない" in home_rules or "既存サイト文言" in home_rules
    assert "TOP踏襲" in home_rules or "踏襲しない" in home_rules
    about = next(p for p in bp["pages"] if p["slug"] == "about")
    assert about.get("reference_url")  # Drive rewrite note from ライティング備考
    about_seeds = " ".join(str(s) for s in (about.get("content_seeds") or []))
    assert "業務内容" in about_seeds or "生活サポート" in about_seeds
    push = about.get("writing_push_points") or []
    assert any("見積" in str(p) for p in push)
    assert any("保証" in str(p) for p in push)
    ren = bp["renewal"]
    assert ren["existing_url"] == "https://voltsdenkikouji.com/"
    assert bp["stats"]["seo_pages"] == 15
    assert bp["stats"]["tag_pages"] == 10
    assert bp["stats"]["nav_pages"] >= 8
    assert bp.get("blueprint_version") == 1
    write = pages_to_write(bp)
    assert len(write) >= 20
    assert any(p.get("slug") == "seo-1" for p in write)


def test_finalize_type2_blueprint():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    partial = build_site_blueprint(hearing)
    partial["pages"] = partial["pages"][:5]
    finalized = finalize_type2_blueprint(partial, hearing)
    assert len(finalized["pages"]) >= 8
    assert finalized.get("blueprint_version") == 1
    assert finalized["production_type"] == ProductionType.TYPE2_RENEWAL.value
