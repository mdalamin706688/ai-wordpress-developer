"""Header-page AI merge (static gnav pages; no dynamic sub pages)."""

from pathlib import Path

from ai_agent.api.lab import _run_pages
from ai_agent.pipeline.hearing_adapter import parse_hearing_csv
from ai_agent.pipeline.prompt_rules import header_ai_page_ids
from ai_agent.pipeline.section_pages import merge_header_page_copies, merge_top_service_copies
from ai_agent.pipeline.site_composer import compose_site_draft

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "demo" / "hearing-sheet.csv"


def _copy(heading: str, slug: str) -> dict:
    return {
        "title": f"店｜{heading}",
        "slug": slug,
        "heading": heading,
        "lead": "リード文です。",
        "body_paragraphs": [
            "コンセプト段落。",
            "メニュー段落 アロマ。",
            "アクセス段落。",
            "営業時間段落。",
            "予約段落。",
            "締めの段落。",
        ],
        "cta": "ご予約はこちら",
        "notes": "",
    }


def test_run_pages_default_header():
    pages = _run_pages(None)
    assert "top" in pages
    assert "service" in pages
    assert "concept" in pages
    assert "menu" in pages
    assert "access" in pages
    assert "faq" in pages
    assert "feature" in pages
    assert "blog" not in pages  # shell only — no AI write
    assert "column" not in pages
    assert _run_pages("top") == ["top"]
    assert _run_pages("service") == ["service"]
    assert _run_pages("concept") == ["concept"]


def test_header_ai_skips_empty_optionals():
    hearing = {"business_name": "店", "menu": []}
    pages = header_ai_page_ids(hearing=hearing)
    assert "greeting" not in pages
    assert "reviews" not in pages
    hearing2 = {**hearing, "staff": "山田", "reviews": ["良かった"]}
    pages2 = header_ai_page_ids(hearing=hearing2)
    assert "greeting" in pages2
    assert "reviews" in pages2


def test_merge_attaches_ai_service_and_top():
    hearing, _ = parse_hearing_csv(SHEET.read_text(encoding="utf-8"))
    top = _copy(hearing.get("catchcopy") or "TOP見出し", "home")
    top["body_paragraphs"][0] = hearing["concept"]
    top["body_paragraphs"][1] = " ".join(
        f"{m['name']} {m.get('duration')} {m.get('price')}" for m in hearing["menu"]
    )
    service = _copy("サービス案内", "service")
    service["body_paragraphs"][0] = "サービス導入：" + hearing["concept"]
    for i, m in enumerate(hearing["menu"]):
        if i + 1 < len(service["body_paragraphs"]):
            service["body_paragraphs"][i + 1] = f"{m['name']}の説明。"

    merged = merge_top_service_copies(hearing, top, service)
    assert merged["_page"] == "top"
    assert isinstance(merged.get("_service_copy"), dict)
    assert merged["_sections"]["top"]["page"] == "top"
    assert merged["_sections"]["service"]["page"] == "service"
    assert len(merged["_sections"]["service"]["services"]) == len(hearing["menu"])
    assert "concept" in merged["_sections"]
    assert "faq" in merged["_sections"]

    wp = compose_site_draft(hearing, merged)
    pages = {p["id"]: p for p in wp["pages"]}
    assert pages["home"]["heading"] == top["heading"]
    assert pages["service"]["heading"] == service["heading"]
    assert any("アロマ" in p or "サービス" in p for p in pages["service"]["body_paragraphs"])
    for need in ("concept", "menu", "faq", "feature", "access", "blog", "column", "reviews"):
        assert need in pages


def test_merge_header_page_copies_multi():
    hearing, _ = parse_hearing_csv(SHEET.read_text(encoding="utf-8"))
    copies = {
        "top": _copy("TOP", "home"),
        "concept": _copy("コンセプト", "concept"),
        "service": _copy("サービス", "service"),
        "menu": _copy("メニュー", "menu"),
        "access": _copy("アクセス", "access"),
    }
    copies["top"]["body_paragraphs"][0] = hearing["concept"]
    merged = merge_header_page_copies(hearing, copies)
    assert set(merged["_page_copies"]) >= {"top", "concept", "service", "menu", "access"}
    assert merged["_sections"]["concept"]["page"] == "concept"
    site = compose_site_draft(hearing, merged)
    assert site["published"] is False
    assert len(site["pages"]) >= 11
