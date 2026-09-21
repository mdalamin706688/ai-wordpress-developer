"""V2 Type 3 (サテライト) hearing parser + blueprint tests."""

import os
from pathlib import Path

from ai_agent.v2.blueprint import build_site_blueprint
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.production_types import ProductionType
from ai_agent.v2.prompt_rules import format_v2_page_rules
from ai_agent.v2.writer import pages_leave_blank, pages_to_write

SAMPLE = Path(__file__).resolve().parents[1] / "demo" / "v2" / "samples" / "type3-sateraito.csv"
# Optional local client CSV folder (set BBS_CLIENT_CSV_DIR to enable extra fixture tests).
_client_dir_env = os.environ.get("BBS_CLIENT_CSV_DIR", "").strip()
CLIENT_DIR = Path(_client_dir_env).expanduser() if _client_dir_env else Path()


def _client_csv() -> Path | None:
    if not CLIENT_DIR or not CLIENT_DIR.is_dir():
        return None
    matches = list(CLIENT_DIR.glob("【サテライト】ヒア*後.csv"))
    return matches[0] if matches else None


def test_parse_type3_sateraito_csv():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    assert hearing["production_type"] == ProductionType.TYPE3_SATELLITE.value
    assert hearing["production_label"] == "サテライト"
    assert len(hearing["pages"]) == 5
    assert len(hearing["reference_sites"]) >= 2
    assert len(hearing["focus_keywords"]) == 5
    assert len(hearing["tag_keywords"]) == 10
    assert len(hearing["seo_pages"]) == 15
    assert len(hearing["tag_pages"]) == 10
    wg = hearing.get("writing_guidance") or {}
    assert "writing_notes" in wg
    assert hearing.get("page_directives") is not None


def test_client_hearing_directives_and_writing_fields():
    client = _client_csv()
    if not client:
        return
    hearing = parse_hearing_sheet(client.read_text(encoding="utf-8-sig"))
    directives = hearing.get("page_directives") or {}
    assert directives.get("menu", {}).get("leave_blank") is True
    assert "FAQ" in str(directives.get("faq", {}).get("reference_url") or "").upper()
    wg = hearing.get("writing_guidance") or {}
    assert wg.get("selling_points")
    assert wg.get("cv_destination")


def test_type3_blueprint_satellite_template():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    assert bp["production_type"] == ProductionType.TYPE3_SATELLITE.value
    assert bp["clone_mode"] == "bbs_satellite_template"
    assert bp["pages"][0]["type"] == "top_satellite"
    home_ids = [s["id"] for s in bp["pages"][0]["sections"]]
    assert "top_catchphrase" in home_ids
    assert "business_info" in home_ids
    assert "cta" in home_ids
    assert "lead" in home_ids
    assert any(i.startswith("selling_point_") for i in home_ids) or any(
        i.startswith("service_teaser_") for i in home_ids
    )
    assert bp["pages"][0]["content_seeds"] == hearing["focus_keywords"]
    slugs = [p["slug"] for p in bp["pages"]]
    assert slugs[:5] == ["home", "concept", "service", "faq", "greeting"]
    for required in ("access", "blog", "reviews", "contact", "sitemap", "privacy", "column"):
        assert required in slugs
    # page composition ② — AI blog when AIサポート=あり
    assert "ai-blog" in slugs
    # Empty 料金表 is omitted from the site map (not kept as a blank page).
    if hearing.get("page_directives", {}).get("menu", {}).get("leave_blank"):
        assert "menu" not in slugs
        omitted = bp.get("omitted_pages") or []
        assert any(str(r.get("slug")) == "menu" for r in omitted if isinstance(r, dict))
        assert bp["stats"].get("omitted_pages", 0) >= 1
    else:
        assert "menu" in slugs
    sat = bp["satellite"]
    assert sat["domain"] == "taiyotoso.jp"
    assert "https://taiyotoso.co.jp/" in sat["main_site_urls"]
    assert bp["stats"]["seo_pages"] == 15
    assert bp["stats"]["tag_pages"] == 10
    assert bp["stats"]["total_sections"] >= 124
    assert bp["stats"].get("write_pages", 0) >= 30
    assert bp["stats"]["nav_pages"] >= 12
    assert bp.get("blueprint_version", 0) >= 3
    assert bp["ai_stages"]["planner"] == "complete"
    assert "warnings" not in bp


def test_type3_blueprint_dynamic_prompt_sections():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    from ai_agent.v2.section_rules import prompt_sections_from_blueprint

    catalog = prompt_sections_from_blueprint(bp)
    assert catalog.get("dynamic") is True
    assert len(catalog.get("tabs") or []) >= 1
    home = None
    for tab in catalog["tabs"]:
        if tab.get("id") == "home":
            home = tab
            break
    assert home is not None
    assert len(home.get("items") or []) >= 1
    assert all(it.get("rule") for it in home["items"])
    for page in bp["pages"] + bp["seo_pages"] + bp["tag_pages"]:
        for sec in page.get("sections") or []:
            assert sec.get("rule")


def test_pages_to_write_includes_seo_and_tag():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    pages = pages_to_write(bp)
    slugs = [p.get("slug") for p in pages]
    assert "home" in slugs
    assert "seo-1" in slugs
    assert "tag-1" in slugs
    assert len(pages) >= 7 + 15 + 10 - 1  # minus blank menu if flagged
    blank = pages_leave_blank(bp)
    # Menu leave_blank pages are omitted from the blueprint.
    # Reviews/greeting may stay in nav with force_blank_copy (empty AI-2 text).
    assert all(p.get("force_blank_copy") for p in blank)
    assert not any(p.get("leave_blank") for p in blank)
    if hearing.get("page_directives", {}).get("menu", {}).get("leave_blank"):
        assert "menu" not in slugs
        assert any(str(r.get("slug")) == "menu" for r in (bp.get("omitted_pages") or []))


def test_tag_page_rules_are_keyword_first():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    tag9 = next(p for p in bp["tag_pages"] if p["slug"] == "tag-9")
    assert tag9["nav_label"] == "アフターフォロー" or "アフター" in tag9["nav_label"]
    assert tag9.get("tag_keyword") or (tag9.get("content_seeds") or [None])[0]
    labels = [s["label"] for s in tag9["sections"]]
    assert "Tag intro" in labels or "Tag point 1" in labels
    assert any(s["id"] == "tag_intro" for s in tag9["sections"])
    assert any(s["id"] == "keyword" for s in tag9["sections"])
    intro = next(s for s in tag9["sections"] if s["id"] == "tag_intro")["rule"]
    assert "主キーワード" in intro or "タグ" in intro
    assert "アフター" in intro
    assert "項目内容: アフター" not in intro  # not the old dump style
    rules = format_v2_page_rules(tag9, hearing)
    assert "タグキーワード用ランディング" in rules
    assert "主キーワード" in rules

def test_seo_page_rules_include_hearing_parts():
    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    seo = bp["seo_pages"][0]
    rules = format_v2_page_rules(seo, hearing)
    assert "SEO冒頭指示" in rules or "おまかせ" in rules
    assert "intro" in rules


def test_satellite_lab_config_overrides_standard_template():
    from ai_agent.v2.prompt_rules import (
        apply_satellite_lab_config,
        default_satellite_user_template,
        is_standard_site_user_template,
        resolve_satellite_write_prompts,
    )

    assert is_standard_site_user_template("body_paragraphs 必ず6要素")
    cfg = {
        "user_prompt_template": "ページ: top\nbody_paragraphs",
        "system_prompt": "body_paragraphs 必ず6段落",
        "prompt_sections": {"tabs": [{"id": "top", "items": []}]},
    }
    apply_satellite_lab_config(cfg)
    assert cfg["prompt_sections"]["source"] == "pending"
    assert cfg["prompt_sections"]["tabs"] == []
    assert "sections (object)" in cfg["user_prompt_template"]
    assert cfg["user_prompt_template"] == default_satellite_user_template()
    assert "body_paragraphs" not in cfg["system_prompt"]

    sys_p, user_p = resolve_satellite_write_prompts(
        {"user_prompt_template": "ページ: top\nbody_paragraphs", "system_prompt": "body_paragraphs"}
    )
    assert "sections (object)" in user_p
    assert "body_paragraphs" not in sys_p


def test_v2_planner_model_roles():
    from ai_agent.v2.pipeline_roles import (
        v2_planner_model,
        v2_planner_model_ids,
        v2_writer_model,
        validate_v2_model_roles,
        V2ModelRoleError,
    )

    assert v2_planner_model(["gemini-3.5-flash-lite"]) == "gemini-3.5-flash-lite"
    assert v2_planner_model(["glm-4.5-flash", "gemini-3.5-flash-lite"]) == "glm-4.5-flash"
    assert v2_planner_model_ids(["glm-4.5-flash"]) == ["glm-4.5-flash"]
    assert v2_writer_model(["glm-4.5-flash"]) == ""
    assert v2_writer_model(["glm-4.5-flash", "gemini-3.5-flash-lite"]) == "gemini-3.5-flash-lite"
    planner, writer = validate_v2_model_roles(["glm-4.5-flash", "gemini-3.5-flash-lite"])
    assert planner == "glm-4.5-flash" and writer == "gemini-3.5-flash-lite"
    try:
        validate_v2_model_roles(["glm-4.5-flash", "glm-4.5-flash"])
        assert False, "expected duplicate model rejection"
    except V2ModelRoleError:
        pass


def test_parse_planner_sections_json():
    from ai_agent.v2.section_planner import parse_planner_sections, strip_blueprint_section_content

    raw = '{"sections": [{"id": "extra_block", "label": "Extra", "mode": "generate", "rule": "店名と重点ワード"}]}'
    page = {"slug": "home", "type": "top_satellite"}
    out = parse_planner_sections(raw, page=page)
    ids = [s["id"] for s in out]
    assert "top_catchphrase" in ids  # catalog merged
    assert "extra_block" in ids  # AI-1 extra kept
    assert "business_info" in ids
    assert "text" not in out[0]
    extra = next(s for s in out if s["id"] == "extra_block")
    assert extra["mode"] == "generate"

    bad = '{"sections": [{"id": "top_catchphrase", "label": "TOP catchphrase", "mode": "generate", "rule": "x", "text": "見出し"}]}'
    try:
        parse_planner_sections(bad, page=page)
        assert False, "expected content key rejection"
    except ValueError as exc:
        assert "AI-2 only" in str(exc)

    bp = {
        "pages": [
            {
                "slug": "home",
                "sections": [
                    {"id": "top_catchphrase", "label": "TOP catchphrase", "mode": "generate", "rule": "r", "text": "bad"},
                ],
            }
        ]
    }
    strip_blueprint_section_content(bp)
    assert "text" not in bp["pages"][0]["sections"][0]


def test_planner_page_counts():
    from ai_agent.v2.blueprint import build_site_blueprint
    from ai_agent.v2.section_planner import count_planner_pages, page_needs_llm_planner

    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    llm_n, total_n = count_planner_pages(bp)
    # 38 when 料金表 present; 37 when empty 料金表 is omitted from the site map.
    assert total_n >= 37
    assert llm_n <= 12
    assert llm_n < total_n
    if hearing.get("page_directives", {}).get("menu", {}).get("leave_blank"):
        assert total_n == bp["stats"]["all_pages"]
        assert "menu" not in [p.get("slug") for p in bp["pages"]]
        assert bp["stats"].get("omitted_pages", 0) >= 1
    else:
        assert total_n >= 38
    blog = next(p for p in bp["pages"] if p["slug"] == "blog")
    assert page_needs_llm_planner(blog, page_group="nav") is False
    assert page_needs_llm_planner(bp["seo_pages"][0], page_group="seo") is False
    assert page_needs_llm_planner(bp["pages"][0], page_group="nav") is True


def test_finalize_type3_blueprint():
    from ai_agent.v2.blueprint import build_site_blueprint, finalize_type3_blueprint

    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    partial = build_site_blueprint(hearing)
    partial["pages"] = partial["pages"][:7]
    finalized = finalize_type3_blueprint(partial, hearing)
    assert len(finalized["pages"]) >= 12
    assert finalized.get("blueprint_version") == 3
    assert finalized["stats"]["total_sections"] >= 120


def test_merge_type3_blueprint_pages():
    from ai_agent.v2.blueprint import build_site_blueprint, merge_type3_blueprint_pages

    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    shell = build_site_blueprint(hearing)
    partial = build_site_blueprint(hearing)
    partial["pages"] = partial["pages"][:7]
    partial["stats"] = {"nav_pages": 7, "total_sections": 24}
    partial.pop("blueprint_version", None)
    merged = merge_type3_blueprint_pages(partial, shell)
    assert len(merged["pages"]) >= 12
    assert merged.get("blueprint_version") == 3
    home = next(p for p in merged["pages"] if p["slug"] == "home")
    assert home.get("sections")


def test_inject_missing_type3_nav_pages():
    from ai_agent.v2.blueprint import build_site_blueprint, inject_missing_type3_nav_pages

    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    old_pages = (bp.get("pages") or [])[:7]
    bp["pages"] = old_pages
    bp["stats"] = {"nav_pages": 7, "total_sections": 24, "write_pages": 32}
    bp["blueprint_version"] = 1
    assert inject_missing_type3_nav_pages(bp, hearing) is True
    assert len(bp["pages"]) >= 12
    assert bp.get("blueprint_version") == 3
    slugs = [p["slug"] for p in bp["pages"]]
    for required in ("blog", "reviews", "contact", "sitemap", "privacy", "column"):
        assert required in slugs


def test_refresh_blueprint_stats():
    from ai_agent.v2.blueprint import build_site_blueprint, refresh_blueprint_stats
    from ai_agent.v2.export import blueprint_to_section_rows

    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    rows = blueprint_to_section_rows(bp)
    bp["stats"] = {"total_sections": 24, "write_pages": None}
    refresh_blueprint_stats(bp)
    assert bp["stats"]["total_sections"] == len(rows)
    assert bp["stats"]["write_pages"] is not None
    assert bp["stats"]["nav_pages"] >= 12


def test_blueprint_export_rows_have_empty_text():
    from ai_agent.v2.export import blueprint_to_section_rows

    text = SAMPLE.read_text(encoding="utf-8-sig")
    hearing = parse_hearing_sheet(text)
    bp = build_site_blueprint(hearing)
    rows = blueprint_to_section_rows(bp)
    assert rows
    assert all(str(r.get("text") or "") == "" for r in rows)


def test_v2_pipeline_roles():
    from ai_agent.v2.pipeline_roles import v2_active_model_ids, v2_pipeline_roles

    w, q, v, mode = v2_pipeline_roles(["glm-4.5-flash"])
    assert mode == "sections_only"
    assert w == ""

    w, q, v, mode = v2_pipeline_roles(["glm-4.5-flash", "gemini-3.5-flash-lite"])
    assert mode == "write"
    assert w == "gemini-3.5-flash-lite"
    assert q == "" and v == []
    assert v2_active_model_ids(["glm-4.5-flash", "gemini-3.5-flash-lite"]) == ["gemini-3.5-flash-lite"]

    w, q, v, mode = v2_pipeline_roles([
        "glm-4.5-flash", "gemini-3.5-flash-lite", "glm-4.7-flash", "nvidia-minimax-m3",
    ])
    assert w == "gemini-3.5-flash-lite"
    assert q == "" and v == []


def test_parse_v2_sections_json():
    from ai_agent.v2.writer import parse_v2_sections_json

    raw = '{"sections": {"top_catchphrase": "見出し", "menu": "コースA ¥1000"}}'
    out = parse_v2_sections_json(raw)
    assert out["top_catchphrase"] == "見出し"
    assert "menu" in out

    flat = '{"top_catchphrase": "A", "lead": "B", "cta": "C"}'
    out2 = parse_v2_sections_json(flat, expected_ids=["top_catchphrase", "lead", "cta"])
    assert out2["top_catchphrase"] == "A"
    assert out2["lead"] == "B"
