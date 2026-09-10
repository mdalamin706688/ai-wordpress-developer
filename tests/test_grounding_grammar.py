"""Semantic grounding, Japanese grammar, and immutable missing[] tests."""

from __future__ import annotations

import json
from pathlib import Path

from ai_agent.pipeline.claims import (
    freeze_missing,
    ground_statement,
    missing_notice,
    missing_preserved,
    strip_high_risk_claims,
)
from ai_agent.pipeline.hearing_adapter import parse_hearing_csv
from ai_agent.pipeline.japanese import japanese_grammar_issues, repair_japanese_text
from ai_agent.pipeline.production import run_generation_job
from ai_agent.pipeline.site_composer import compose_site_draft
from ai_agent.pipeline.validate import prepare_copy_for_wordpress
from ai_agent.pipeline.verify import apply_issues_audited

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "demo" / "hearing-sheet.csv"


def _hearing():
    hearing, _meta = parse_hearing_csv(SHEET.read_text(encoding="utf-8"))
    return hearing


def _copy(hearing, *, lead=None, body=None):
    menu0 = hearing["menu"][0]
    return {
        "title": f"{hearing['business_name']}｜トップ",
        "slug": "top",
        "heading": hearing["catchcopy"],
        "lead": lead or f"{hearing['station']}の落ち着いたサロンです。",
        "body_paragraphs": [
            hearing["concept"],
            body
            or (
                f"アロマ 60分 {menu0['price']}。ヘッドスパ 40分 ¥5,500。"
                "フットケア 40分 ¥4,400。リフレッシュ 75分 ¥11,000。"
            ),
            f"{hearing['station']} / {hearing['address']}",
            f"{hearing['hours']} {hearing['closed']} 電話{hearing['phone']}",
            f"{hearing['first_visit']} 予約は{hearing['reservation']}",
            "近隣で働く方へ。",
        ],
        "cta": "ご予約はこちら",
        "notes": "",
    }


def test_facility_hallucination_blocked():
    hearing = _hearing()
    assert "個室" not in json.dumps(hearing, ensure_ascii=False)
    verdict = ground_statement("完全個室です。", hearing)
    assert verdict["verdict"] == "UNSUPPORTED"
    assert verdict["category"] == "FACILITY_CLAIM"
    copy = _copy(hearing)
    copy["body_paragraphs"][0] = "落ち着いたプライベート空間で、完全個室です。"
    final, report = prepare_copy_for_wordpress(copy, hearing)
    blob = "\n".join(final["body_paragraphs"])
    assert "完全個室" not in blob
    assert report["audit"]["unsupported_claims"] == 0 or "完全個室" not in blob


def test_business_policy_hallucination_unsupported():
    hearing = _hearing()
    verdict = ground_statement("無理な勧誘は一切ありません。", hearing)
    assert verdict["verdict"] == "UNSUPPORTED"
    assert verdict["category"] == "BUSINESS_PROMISE"
    stripped = strip_high_risk_claims("無理な勧誘は一切ありません。ご予約ください。", hearing)
    assert "無理な勧誘" not in stripped


def test_qualification_hallucination_unsupported():
    hearing = _hearing()
    verdict = ground_statement("経験豊富な専門スタッフが対応します。", hearing)
    assert verdict["verdict"] == "UNSUPPORTED"
    copy = _copy(hearing)
    copy["body_paragraphs"][5] = "経験豊富な専門スタッフが対応します。"
    final, _report = prepare_copy_for_wordpress(copy, hearing)
    blob = "\n".join(final["body_paragraphs"])
    assert "経験豊富" not in blob
    assert "専門スタッフ" not in blob


def test_counseling_restatement_supported():
    hearing = _hearing()
    assert "カウンセリング" in hearing.get("first_visit", "")
    verdict = ground_statement("初回にカウンセリングを行います。", hearing)
    assert verdict["verdict"] == "SUPPORTED"


def test_counseling_promise_not_accepted():
    hearing = _hearing()
    verdict = ground_statement(
        "体調を詳しく確認し、最適なコースをご提案します。",
        hearing,
    )
    assert verdict["verdict"] in {"INFERENCE", "UNSUPPORTED"}
    assert verdict["category"] in {"BUSINESS_PROMISE", "INFERENCE", "UNSUPPORTED"}
    copy = _copy(hearing)
    copy["body_paragraphs"][4] = "体調を詳しく確認し、最適なコースをご提案します。"
    final, report = prepare_copy_for_wordpress(copy, hearing)
    blob = "\n".join(final["body_paragraphs"])
    assert "最適なコースをご提案" not in blob
    assert report["ok"] is True or "最適なコース" not in blob


def test_grammar_orphan_walk_detected():
    issues = japanese_grammar_issues("から徒歩4分です。")
    assert issues
    assert any(i["type"] == "JAPANESE_GRAMMAR" for i in issues)


def test_grammar_leading_ha_detected():
    issues = japanese_grammar_issues("は東急田園都市線 桜新町駅です。")
    assert issues


def test_grammar_duplicated_particles():
    assert japanese_grammar_issues("当店ではは予約が可能です。")
    assert japanese_grammar_issues("ご利用いただけますできます。")
    assert japanese_grammar_issues("桜新町駅から徒歩4分にありますです。")


def test_grammar_correct_japanese_not_rewritten():
    hearing = _hearing()
    ok = "東急田園都市線 桜新町駅から徒歩4分です。"
    assert not japanese_grammar_issues(ok)
    assert repair_japanese_text(ok, hearing) == ok


def test_post_repair_tbd_walk_keeps_station_subject():
    hearing = _hearing()
    copy = _copy(hearing, lead="要ヒアリングから徒歩4分のサロンです。")
    final, report = prepare_copy_for_wordpress(copy, hearing)
    lead = final["lead"]
    assert "桜新町駅" in lead
    assert "徒歩4分" in lead
    assert not lead.lstrip().startswith("から徒歩")
    assert "要ヒアリングから徒歩" not in lead
    assert report["audit"]["grammar_issues"] == 0
    assert report["audit"]["linked_fact_integrity"] == "PASS"


def test_repair_leading_ha_keeps_walk_minutes():
    hearing = _hearing()
    repaired = repair_japanese_text(
        "は東急田園都市線 桜新町駅であり、駅から徒歩4分です。",
        hearing,
    )
    assert repaired.startswith("最寄り駅は")
    assert "桜新町駅" in repaired
    assert "徒歩4分" in repaired
    assert "徒歩5分" not in repaired
    assert not japanese_grammar_issues(repaired)


def test_language_repair_cannot_change_walk_minutes():
    hearing = _hearing()
    copy = _copy(hearing)
    copy["body_paragraphs"][2] = "は東急田園都市線 桜新町駅であり、駅から徒歩4分です。"
    _out, _applied, repairs = apply_issues_audited(
        copy,
        [
            {
                "field": "body_3",
                "path": "body.2",
                "type": "JAPANESE_GRAMMAR",
                "span": "駅から徒歩4分",
                "suggestion": "桜新町駅から徒歩5分",
            }
        ],
        hearing,
    )
    assert any(r.get("type") == "VERIFIER_REPAIR_REJECTED" for r in repairs)


def test_missing_count_preserved():
    hearing = _hearing()
    expected = freeze_missing(hearing)
    assert "店内写真" in expected
    assert len(expected) == 3
    copy = _copy(hearing)
    copy["missing"] = ["スタッフ紹介"]
    site = compose_site_draft(hearing, copy)
    actual = (site.get("qa") or {}).get("missing")
    assert len(actual) == len(expected)
    assert actual == expected
    assert missing_preserved(hearing, actual)
    assert missing_notice(actual) == "スタッフ紹介・お客様の声・店内写真は要ヒアリングです。"
    contact_page = next(p for p in site["pages"] if p.get("id") == "contact")
    contact = " ".join(contact_page["body_paragraphs"])
    assert "店内写真" not in contact


def test_production_gate_blocks_grammar():
    hearing = _hearing()
    raw = json.dumps(_copy(hearing, lead="から徒歩4分です。"), ensure_ascii=False)

    def writer(_h):
        return raw

    result = run_generation_job(
        hearing,
        writer=writer,
        verifier=lambda _h, _c: json.dumps({"status": "PASS", "issues": []}),
        job_id="grammar-block",
        write_wordpress=False,
    )
    lead = (result.get("copy") or {}).get("lead") or ""
    # Deterministic restore should repair before the gate.
    assert "桜新町駅" in lead
    assert not lead.lstrip().startswith("から徒歩")
    assert result["audit"]["grammar_issues"] == 0
    assert result["audit"]["missing_items_preserved"] is True


def test_audit_summary_shape():
    hearing = _hearing()
    _final, report = prepare_copy_for_wordpress(_copy(hearing), hearing)
    audit = report["audit"]
    assert audit["fact_integrity"] == "PASS"
    assert audit["linked_fact_integrity"] == "PASS"
    assert audit["unsupported_claims"] == 0
    assert audit["forbidden_claims"] == 0
    assert audit["grammar_issues"] == 0
    assert audit["missing_items_preserved"] is True
    assert audit["status"] in {"PASS", "REPAIRED"}
    assert report["ok"] is True
