"""WordPress sections UI export follows TOP/Service checklist (not body_1–6)."""

from pathlib import Path

from ai_agent.api.lab import build_wp_sections
from ai_agent.pipeline.hearing_adapter import parse_hearing_csv
from ai_agent.pipeline.site_composer import compose_site_draft

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "demo" / "hearing-sheet.csv"


def test_build_wp_sections_uses_top_service_checklist():
    hearing, _ = parse_hearing_csv(SHEET.read_text(encoding="utf-8"))
    copy = {
        "title": f"{hearing['business_name']}｜公式",
        "slug": "home",
        "heading": hearing.get("catchcopy") or "見出し",
        "lead": f"{hearing['station']}のサロンです。",
        "body_paragraphs": [
            hearing["concept"],
            "メニュー案内",
            hearing["station"],
            hearing["hours"],
            hearing.get("reservation") or "電話",
            "お待ちしています。",
        ],
        "cta": "ご予約はこちら",
        "notes": "",
    }
    wp = compose_site_draft(hearing, copy)
    sections = build_wp_sections(copy, wp, hearing=hearing)
    ids = [s["id"] for s in sections]
    assert "top_title" in ids or "home_title" in ids
    assert "top_hero" in ids
    assert "top_about" in ids
    assert "top_menu" in ids
    assert "top_access" in ids
    assert "top_reservation" in ids
    assert "service_hero" in ids
    assert "service_services" in ids
    assert "service_reservation" in ids
    assert "concept_hero" in ids
    assert "menu_items" in ids or "menu_title" in ids
    assert "faq_items" in ids or "faq_title" in ids
    assert "access_details" in ids or "access_title" in ids
    assert "blog_hero" in ids or "blog_title" in ids
    assert "body_1" not in ids
    assert "wp_title" not in ids
    hero = next(s for s in sections if s["id"] == "top_hero")
    assert hearing["business_name"] in hero["text"]
    services = next(s for s in sections if s["id"] == "service_services")
    assert "アロマ" in services["text"] or any(
        m["name"] in services["text"] for m in hearing.get("menu") or []
    )
