"""Page composition: ① must / ② conditional / ③ page-add."""

from __future__ import annotations

from pathlib import Path

from ai_agent.v2.blueprint import build_site_blueprint
from ai_agent.v2.hearing_parser import parse_hearing_sheet

MUST = ("home", "access", "blog", "contact", "sitemap", "privacy")
SAMPLES = Path(__file__).resolve().parents[1] / "demo" / "v2" / "samples"


def _slugs(bp: dict) -> set[str]:
    return {str(p.get("slug") or "") for p in (bp.get("pages") or [])}


def test_page_composition_must_pages_all_types():
    for name in (
        "type1-shinki.csv",
        "type2-renewal.csv",
        "type3-satellite.csv",
        "type4-satellite-renewal.csv",
    ):
        hearing = parse_hearing_sheet((SAMPLES / name).read_text(encoding="utf-8-sig"))
        bp = build_site_blueprint(hearing)
        slugs = _slugs(bp)
        for slug in MUST:
            assert slug in slugs, f"{name}: missing must page {slug}"


def test_page_composition_reviews_conditional():
    t1 = parse_hearing_sheet((SAMPLES / "type1-shinki.csv").read_text(encoding="utf-8-sig"))
    assert not t1["flags"]["include_reviews"]
    assert "reviews" not in _slugs(build_site_blueprint(t1))

    t3 = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    assert t3["flags"]["include_reviews"]
    bp3 = build_site_blueprint(t3)
    assert "reviews" in _slugs(bp3)
    reviews = next(p for p in bp3["pages"] if p["slug"] == "reviews")
    # type3 sample has 表示する only — keep page, force blank copy
    assert reviews.get("force_blank_copy") is True
    assert all(str(s.get("mode")) == "blank" for s in reviews["sections"])

    t4 = parse_hearing_sheet((SAMPLES / "type4-satellite-renewal.csv").read_text(encoding="utf-8-sig"))
    assert not t4["flags"]["include_reviews"]  # 表示しない skipped
    assert "reviews" not in _slugs(build_site_blueprint(t4))


def test_greeting_force_blank_without_staff_facts():
    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    greeting = next((p for p in bp["pages"] if p.get("slug") == "greeting"), None)
    if greeting is None:
        return
    # Sample greeting page typically has no real staff body → blank copy
    assert greeting.get("force_blank_copy") is True or any(
        str(s.get("mode")) == "blank" for s in (greeting.get("sections") or [])
    )


def test_seo_rules_require_unique_landing_copy():
    from ai_agent.v2.section_rules import dynamic_section_rule

    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    seo = (bp.get("seo_pages") or [None])[0]
    assert seo is not None
    sec = next(
        (s for s in (seo.get("sections") or []) if str(s.get("id") or "") in {"seo_intro", "intro_body", "intro"}),
        None,
    ) or next(
        (s for s in (seo.get("sections") or []) if str(s.get("id") or "") == "intro"),
        {"id": "seo_intro", "mode": "generate"},
    )
    rule = dynamic_section_rule(sec, seo, hearing)
    assert "UNIQUE LANDING COPY" in rule
    assert "主角度" in rule
    assert "社名由来" in rule or "太陽さん" in rule

def test_seo_pages_get_distinct_primary_angles():
    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    seos = bp.get("seo_pages") or []
    assert len(seos) == 15
    primaries = [str(p.get("seo_primary_keyword") or "") for p in seos]
    assert all(primaries)
    # Not every page shares the identical seed list / primary
    assert len(set(primaries)) >= 5
    seeds = [tuple(p.get("content_seeds") or []) for p in seos]
    assert len(set(seeds)) >= 5
    # Labels should reflect primary, not generic SEOページN for all
    assert seos[0]["nav_label"] == primaries[0]
    assert "SEOページ1" != seos[0]["nav_label"] or primaries[0].startswith("SEO")


def test_faq_items_blank_when_no_hearing_qa():
    from ai_agent.v2.section_rules import is_faq_qa_section_id
    from ai_agent.v2.writer import enforce_blank_page_copy

    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    faq = next(p for p in bp["pages"] if p["slug"] == "faq")
    assert faq.get("faq_items_blank") is True
    assert faq.get("reference_url")
    items_sec = next(s for s in faq["sections"] if is_faq_qa_section_id(str(s.get("id") or "")))
    assert items_sec.get("mode") == "blank"
    out = enforce_blank_page_copy(
        {
            "faq_hero": "よくある質問",
            "faq_items": "Q:費用は？ A:10万円",
            "items": "Q:費用",
            "faq_list": "よく寄せられる疑問点についてまとめております。",
            "faq_flow_cta": "連絡",
            "cta": "連絡",
        },
        faq,
        hearing,
    )
    assert out.get("faq_items", "") == ""
    assert out.get("items", "") == ""
    assert out.get("faq_list", "") == ""
    assert out.get("faq_hero") == "よくある質問"
    assert out.get("cta") == "連絡"
    assert is_faq_qa_section_id("faq_list")
    assert not is_faq_qa_section_id("faq_hero")


def test_service_list_rule_requires_per_item_lines():
    from ai_agent.v2.section_rules import dynamic_section_rule

    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    bp = build_site_blueprint(hearing)
    service = next(p for p in bp["pages"] if p["slug"] == "service")
    sec = next(
        s
        for s in service["sections"]
        if str(s.get("id") or "") in {"service_list", "services", "items"}
        or (str(s.get("id") or "").startswith("service_") and str(s.get("id") or "")[8:].isdigit())
    )
    rule = dynamic_section_rule(sec, service, hearing)
    assert "title" in rule or "1行" in rule
    assert "創作禁止" in rule or "料金" in rule

def test_enforce_blank_reviews_and_greeting_copy():
    from ai_agent.v2.writer import enforce_blank_page_copy

    hearing = parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))
    out = enforce_blank_page_copy(
        {
            "reviews_intro": {"heading": "お客様の声", "lead": "ご紹介します"},
            "review_items": "",
            "cta": {"label": "予約", "phone": "", "url": "", "line_url": "", "methods": ""},
        },
        {"slug": "reviews", "type": "お客様の声"},
        hearing,
    )
    assert out["reviews_intro"] == {"heading": "", "lead": ""}
    assert out["cta"] == {"label": "", "phone": "", "url": "", "line_url": "", "methods": ""}
    out2 = enforce_blank_page_copy(
        {
            "greeting_intro": {"heading": "代表より", "lead": ""},
            "greeting_profile": {"name": "A", "role": "B", "message": "こんにちは", "career": ""},
        },
        {"slug": "greeting", "type": "スタッフ (代表挨拶・代表のみ)"},
        hearing,
    )
    assert out2["greeting_intro"] == {"heading": "", "lead": ""}
    assert out2["greeting_profile"] == {"name": "", "role": "", "message": "", "career": ""}


def test_page_composition_ai_blog_when_support_yes():
    for name in ("type1-shinki.csv", "type2-renewal.csv", "type3-satellite.csv"):
        hearing = parse_hearing_sheet((SAMPLES / name).read_text(encoding="utf-8-sig"))
        assert hearing["flags"]["include_ai_blog"] is True
        assert "ai-blog" in _slugs(build_site_blueprint(hearing))


def test_page_composition_recruit_when_kind_recruit():
    raw = (SAMPLES / "type1-shinki.csv").read_text(encoding="utf-8-sig")
    # Force 制作種別=リクルート on a copy of headers/values via parser flags override
    hearing = parse_hearing_sheet(raw)
    hearing["flags"]["include_recruit"] = True
    hearing["project"]["production_kind"] = "リクルート"
    hearing["recruit"] = {"enabled": True, "keywords": "正社員募集", "message": "一緒に働きませんか"}
    bp = build_site_blueprint(hearing)
    assert "recruit" in _slugs(bp)


def test_page_composition_page_add_slots_present_as_content_pages():
    """③ — ページの追加 slots become content pages (type1 sample has 7)."""
    hearing = parse_hearing_sheet((SAMPLES / "type1-shinki.csv").read_text(encoding="utf-8-sig"))
    assert len(hearing["pages"]) == 7
    bp = build_site_blueprint(hearing)
    # Concept/service etc. come from page-add, not only must/conditional shells
    slugs = _slugs(bp)
    assert "concept" in slugs or "service" in slugs
