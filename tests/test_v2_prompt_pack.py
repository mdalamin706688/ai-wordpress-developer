"""Per-type (1–4) AI-1 / AI-2 English prompts — hearing sheet is source of truth."""

from __future__ import annotations

from ai_agent.v2.prompt_packs import (
    build_prompt_pack,
    default_ai1_planner_for_type,
    default_ai2_system_for_type,
    default_ai2_user_for_type,
    merge_type_prompts,
)
from ai_agent.v2.prompt_rules import (
    apply_satellite_lab_config,
    resolve_satellite_planner_prompt,
    resolve_satellite_write_prompts,
)


def test_prompt_pack_has_four_type_sections_with_ai1_and_ai2():
    pack = build_prompt_pack()
    assert pack["mode"] == "per_type"
    ids = [s["id"] for s in pack["sections"]]
    assert ids == ["type1", "type2", "type3", "type4"]
    for sec in pack["sections"]:
        assert "hearing" in sec["value"].lower() or "HEARING" in sec["value"]
        assert "hearing-driven" in sec["value"]
        assert "CONTENT SCOPE" in sec["value"]
        assert (
            "hearing-driven structure" in sec["planner_value"]
            or "NESTED" in sec["planner_value"]
            or "CONTENT SECTIONS" in sec["planner_value"]
        )
        assert "{page_rules}" in sec["user_value"]
        assert "{hearing}" in sec["user_value"]
    # Type 1 AI-1: hearing-only structure, JSON id/label/mode/rule, no page copy
    t1 = next(s for s in pack["sections"] if s["id"] == "type1")
    p1 = t1["planner_value"]
    assert p1.startswith("TYPE 1 — hearing-driven structure.")
    assert "Plan section blocks only from THIS hearing sheet" in p1
    assert "Do not invent facts" in p1
    assert "No page copy" in p1
    assert "id, label, mode, rule" in p1
    assert "PAGE LIST CONTEXT" in p1 or "PAGE COMPOSITION" in p1
    # Type 3 AI-1/AI-2: nested slots from PAGE / page_rules (this hearing only)
    t3 = next(s for s in pack["sections"] if s["id"] == "type3")
    assert "PAGE SCOPE" in t3["planner_value"]
    assert "HEARING-DYNAMIC" not in t3["planner_value"]
    assert "NESTED" in t3["planner_value"] or "CONTENT SECTIONS + NESTED" in t3["planner_value"]
    assert "NESTED PATTERN" not in t3["planner_value"]
    assert "Common shapes" not in t3["planner_value"]
    assert "template_hint" in t3["planner_value"].lower() or "PAGE block" in t3["planner_value"]
    assert "PAGE SCOPE" in t3["value"]
    assert "HEARING-DYNAMIC" not in t3["value"]
    assert "page_rules" in t3["value"] or "THIS page" in t3["value"]
    assert "catchphrase" in t3["value"] or "CATCHCOPY" in t3["value"]
    assert "Nested pattern:" not in t3["value"]
    assert "サイト制作目的" in t3["value"] or "SITE BRIEF" in t3["value"] or "lead_gen" in t3["value"]
    assert "PLAYBOOK" in t3["value"]
    assert "lead_gen / recruit" not in t3["value"]
    assert "branch landing site" not in t3["value"]
    # Must not hardcode a static per-page inventory like old concept/TOP dump
    assert "コンセプト:" not in t3["planner_value"]
    assert "代表挨拶:" not in t3["planner_value"]


def test_ai1_fallback_matches_english_pack():
    from ai_agent.v2.section_planner import PLANNER_SYSTEM

    # Fallback is type3 nested pack from this hearing
    assert "PAGE SCOPE" in PLANNER_SYSTEM or "NESTED" in PLANNER_SYSTEM
    assert "HEARING-DYNAMIC" not in PLANNER_SYSTEM
    assert "hero" in PLANNER_SYSTEM.lower()
    assert "Japanese instruction" not in PLANNER_SYSTEM
    # Type 1 dedicated prompt
    t1 = default_ai1_planner_for_type("type1")
    assert t1.startswith("TYPE 1 — hearing-driven structure.")
    assert "No page copy" in t1
    t3 = default_ai1_planner_for_type("type3")
    assert "PAGE SCOPE" in t3
    assert "HEARING-DYNAMIC" not in t3
    assert "template_hint" in t3.lower() or "PAGE block" in t3
    assert "コンセプト:" not in t3

def test_ai2_fallback_matches_english_pack():
    from ai_agent.v2.writer import V2_WRITER_SYSTEM

    assert "CONTENT SCOPE" in V2_WRITER_SYSTEM
    assert "HEARING SHEET IS THE SOURCE OF TRUTH" in V2_WRITER_SYSTEM
    assert "NESTED" in V2_WRITER_SYSTEM or "concept_catchphrase" in V2_WRITER_SYSTEM
    assert "catchphrase" in V2_WRITER_SYSTEM or "CATCHCOPY" in V2_WRITER_SYSTEM

def test_ai1_and_ai2_prompts_differ_across_types():
    assert default_ai1_planner_for_type("type1") != default_ai1_planner_for_type("type2")
    assert default_ai1_planner_for_type("type3") != default_ai1_planner_for_type("type4")
    assert default_ai2_system_for_type("type1") != default_ai2_system_for_type("type4")
    assert default_ai2_user_for_type("type2") != default_ai2_user_for_type("type3")
    tp = merge_type_prompts({})
    planners = {tid: tp[tid]["planner_system_prompt"] for tid in tp}
    assert len(set(planners.values())) == 4


def test_resolve_uses_hearing_production_type_for_ai1_and_ai2():
    cfg = apply_satellite_lab_config({})
    cfg["type_prompts"]["type1"]["system_prompt"] = "T1_AI2"
    cfg["type_prompts"]["type1"]["planner_system_prompt"] = "T1_AI1"
    cfg["type_prompts"]["type1"]["user_prompt_template"] = "T1_USER {page_rules}\n{hearing}"
    cfg["type_prompts"]["type4"]["system_prompt"] = "T4_AI2"
    cfg["type_prompts"]["type4"]["planner_system_prompt"] = "T4_AI1"
    cfg["type_prompts"]["type4"]["user_prompt_template"] = "T4_USER {page_rules}\n{hearing}"

    s1, u1 = resolve_satellite_write_prompts(cfg, production_type="type1")
    p1 = resolve_satellite_planner_prompt(cfg, production_type="type1")
    s4, u4 = resolve_satellite_write_prompts(cfg, production_type="type4")
    p4 = resolve_satellite_planner_prompt(cfg, production_type="type4")

    assert s1 == "T1_AI2" and p1 == "T1_AI1" and "T1_USER" in u1
    assert s4 == "T4_AI2" and p4 == "T4_AI1" and "T4_USER" in u4


def test_shared_generic_planner_migrates_to_type_specific():
    cfg = {
        "type_prompts": {
            "type1": {
                "system_prompt": "TYPE FOCUS (Type 1 — New site):\nold",
                "planner_system_prompt": "You are BBS WordPress section planner (AI-1).\nPlan section BLOCK STRUCTURE",
            }
        }
    }
    out = apply_satellite_lab_config(cfg)
    assert "hearing-driven structure" in out["type_prompts"]["type1"]["planner_system_prompt"]
    assert "hearing-driven content" in out["type_prompts"]["type1"]["system_prompt"]


def test_apply_satellite_exposes_type_prompts():
    out = apply_satellite_lab_config({})
    assert set(out["type_prompts"]) == {"type1", "type2", "type3", "type4"}
    assert out["prompt_pack"]["mode"] == "per_type"
