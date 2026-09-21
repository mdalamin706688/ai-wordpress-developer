"""Type 3 fact-slot enforcement and AI-1 catalog finalize."""

from __future__ import annotations

from pathlib import Path

from ai_agent.v2.fact_slots import (
    enforce_hearing_fact_slots,
    hearing_hours,
    hearing_payment,
    normalize_catchphrase,
    shorten_catchcopy,
)
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.page_catalog import _hearing_selling_seeds, build_top_satellite_sections
from ai_agent.v2.section_planner import finalize_planned_sections, parse_planner_sections

SAMPLES = Path(__file__).resolve().parents[1] / "demo" / "v2" / "samples"


def _hearing():
    return parse_hearing_sheet((SAMPLES / "type3-satellite.csv").read_text(encoding="utf-8-sig"))


def test_hearing_hours_and_payment():
    h = _hearing()
    assert hearing_hours(h) == "8:00–18:00"
    assert "クレジット" in hearing_payment(h)


def test_composed_area_includes_peninsula_and_prefecture():
    h = _hearing()
    area = h["project"]["area"]
    assert "島原半島" in area
    assert "長崎" in area
    assert "・" in area


def test_selling_seeds_pair_titles_with_brackets():
    h = _hearing()
    seeds = _hearing_selling_seeds(h)
    assert seeds
    assert any("地域密着" in s for s in seeds)
    assert any("島原半島" in s or "トータル" in s or "アフター" in s for s in seeds)
    # Broken "]" leftovers from naive 。 split must not appear alone
    assert "]" not in "".join(seeds)
    home = build_top_satellite_sections(hearing=h)
    sell_ids = [s["id"] for s in home if str(s.get("id", "")).startswith("selling_point_")]
    assert len(sell_ids) >= 3


def test_enforce_fills_postal_and_shortens_catchcopy():
    h = _hearing()
    page = {"slug": "home", "type": "top_satellite"}
    sections = {
        "top_catchphrase": {
            "brand_name": "WRONG",
            "catchphrase": "長崎県島原半島を中心に住宅の外壁や屋根などの塗装を請け負う有限会社太陽塗装",
            "short_description": "説明",
        },
        "business_info": {
            "name": "",
            "postal": "",
            "address": "",
            "phone": "",
            "hours": "",
            "closed": "",
            "payment": "",
            "email": "",
            "instagram": "",
        },
        "cta": {"label": "", "phone": "000", "url": "", "line_url": "", "methods": ""},
        "access_details": {
            "station": "",
            "address": "",
            "phone": "",
            "hours": "",
            "closed": "",
            "payment": "",
            "parking": "",
            "map_note": "塗装は天気と付き合う仕事なので、皆さまに太陽さんと親しんでいただけるよう「太陽塗装」という名前になりました。",
            "map_url": "",
        },
    }
    out = enforce_hearing_fact_slots(sections, page, h)
    assert out["business_info"]["postal"] == "859-1302"
    assert out["business_info"]["phone"] == "0120-011-923"
    assert out["top_catchphrase"]["brand_name"] == "有限会社太陽塗装"
    assert out["cta"]["phone"] == "0120-011-923"
    catch = out["top_catchphrase"]["catchphrase"]
    assert 10 <= len(catch) <= 28
    assert "請け負う" not in catch
    assert "島原半島" in catch or "長崎" in catch
    assert out["cta"]["label"]  # lead_gen default
    assert "見積" in out["cta"]["label"] or "相談" in out["cta"]["label"]
    assert "太陽さん" not in out["access_details"]["map_note"]
    assert "所在地" in out["access_details"]["map_note"] or "雲仙市" in out["access_details"]["map_note"]


def test_normalize_moves_long_story_to_short_description():
    h = _hearing()
    long_line = "島原半島を中心に、住宅の外壁や屋根などの塗装を請け負う会社です"
    out = enforce_hearing_fact_slots(
        {
            "top_catchphrase": {
                "brand_name": "",
                "catchphrase": long_line,
                "short_description": "",
            }
        },
        {"slug": "home", "type": "top_satellite"},
        h,
    )
    catch = out["top_catchphrase"]["catchphrase"]
    assert len(catch) <= 28
    assert catch != long_line
    assert out["top_catchphrase"]["short_description"]


def test_shorten_catchcopy_uses_area_industry():
    h = _hearing()
    short = shorten_catchcopy("あ" * 50, h)
    assert "長崎" in short
    assert "外壁塗装" in short
    assert "島原半島" in short
    assert len(short) <= 28
    assert 15 <= len(normalize_catchphrase("", h)) <= 28 or len(normalize_catchphrase("", h)) >= 10


def test_finalize_merges_missing_catalog_and_drops_seo_extras():
    page = {"slug": "home", "type": "top_satellite"}
    planned = [
        {"id": "top_catchphrase", "label": "TOP catchphrase", "mode": "blank", "rule": "x"},
        {"id": "seo_intro_heading", "label": "Bad", "mode": "generate", "rule": "x"},
        {"id": "brand_origin", "label": "Bad2", "mode": "generate", "rule": "x"},
    ]
    out = finalize_planned_sections(planned, page)
    ids = [s["id"] for s in out]
    assert "top_catchphrase" in ids
    assert "business_info" in ids
    assert "cta" in ids
    assert "seo_intro_heading" not in ids
    assert "brand_origin" not in ids
    hero = next(s for s in out if s["id"] == "top_catchphrase")
    assert hero.get("fields")  # nested shape preserved from catalog


def test_parse_planner_finalizes_type3_home():
    page = {"slug": "home", "type": "top_satellite"}
    raw = (
        '{"sections":[{"id":"top_catchphrase","label":"Hero","mode":"generate","rule":"name"},'
        '{"id":"seo_intro_body","label":"X","mode":"generate","rule":"no"}]}'
    )
    out = parse_planner_sections(raw, page=page)
    ids = [s["id"] for s in out]
    assert "business_info" in ids
    assert "seo_intro_body" not in ids
