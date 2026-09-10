"""Section checklist enforcement + TOP/Service page structure."""

from __future__ import annotations

from pathlib import Path

from ai_agent.pipeline.hearing_adapter import parse_hearing_csv
from ai_agent.pipeline.section_enforce import required_section_ids, section_coverage_issues
from ai_agent.pipeline.section_pages import build_section_bundle
from ai_agent.pipeline.site_composer import compose_site_draft
from ai_agent.pipeline.validate import prepare_copy_for_wordpress

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "demo" / "hearing-sheet.csv"


def _hearing():
    hearing, _ = parse_hearing_csv(SHEET.read_text(encoding="utf-8"))
    return hearing


def _full_copy(hearing):
    menu_line = " ".join(
        f"{i['name']} {i.get('duration') or ''} {i.get('price') or ''}".strip()
        for i in hearing.get("menu") or []
    )
    return {
        "title": f"{hearing['business_name']}｜{hearing.get('area') or '公式'}",
        "slug": "top",
        "heading": hearing.get("catchcopy") or "見出し",
        "lead": f"{hearing['station']}。気軽にご利用ください。",
        "body_paragraphs": [
            hearing["concept"],
            menu_line,
            f"{hearing['station']}。{hearing.get('address') or ''}",
            f"{hearing['hours']} {hearing.get('closed') or ''} {hearing['phone']}",
            f"{hearing.get('first_visit') or ''} 予約は{hearing.get('reservation') or '電話'}",
            "近隣の方もお気軽にどうぞ。",
        ],
        "cta": "ご予約はこちら",
        "notes": "",
    }


def test_bundle_has_top_and_service():
    hearing = _hearing()
    bundle = build_section_bundle(hearing, _full_copy(hearing), page="top")
    assert bundle["top"]["page"] == "top"
    assert bundle["service"]["page"] == "service"
    assert len(bundle["service"]["services"]) == len(hearing["menu"])
    assert bundle["top"]["greeting"]["enabled"] is False


def test_compose_attaches_sections_to_home_and_service():
    hearing = _hearing()
    site = compose_site_draft(hearing, _full_copy(hearing))
    ids = [p["id"] for p in site["pages"]]
    for need in (
        "home",
        "concept",
        "service",
        "greeting",
        "menu",
        "faq",
        "feature",
        "access",
        "blog",
        "column",
        "reviews",
        "contact",
    ):
        assert need in ids
    home = next(p for p in site["pages"] if p["id"] == "home")
    svc = next(p for p in site["pages"] if p["id"] == "service")
    assert home["sections"]["page"] == "top"
    assert svc["sections"]["page"] == "service"
    assert "¥8,800" in " ".join(i["price"] for i in home["sections"]["menu"]["items"])


def test_section_gap_blocks_incomplete_copy():
    hearing = _hearing()
    thin = {
        "title": "t",
        "slug": "top",
        "heading": "h",
        "lead": "l",
        "body_paragraphs": ["短い文です。"] * 6,
        "cta": "ご予約はこちら",
        "notes": "",
    }
    gaps = section_coverage_issues(thin, hearing, page="top")
    assert gaps
    assert any(g["type"] == "SECTION_GAP" for g in gaps)


def test_full_copy_covers_required_top_sections():
    hearing = _hearing()
    copy = _full_copy(hearing)
    assert required_section_ids("top", hearing) == [
        "hero",
        "about",
        "concept",
        "menu",
        "access",
        "reservation",
    ]
    assert section_coverage_issues(copy, hearing, page="top") == []
    final, report = prepare_copy_for_wordpress(copy, hearing)
    assert report["ok"] is True
    assert final.get("_sections", {}).get("service", {}).get("page") == "service"


def test_service_page_intent_uses_ai_on_service():
    hearing = _hearing()
    hearing = dict(hearing)
    hearing["target_page"] = "service"
    copy = _full_copy(hearing)
    copy["slug"] = "service"
    copy["title"] = f"サービス｜{hearing['business_name']}"
    copy["heading"] = "サービス"
    site = compose_site_draft(hearing, copy)
    svc = next(p for p in site["pages"] if p["id"] == "service")
    assert svc["slug"] == "service"
    assert svc["sections"]["services"]
