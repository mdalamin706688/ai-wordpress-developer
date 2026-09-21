"""V2 satellite page section rules for AI-2 writer prompts."""

from __future__ import annotations

from typing import Any

from ai_agent.pipeline.prompt_rules import SHARED_PAGE_RULES
from ai_agent.v2.prompt_packs import (
    DEFAULT_AI1_PLANNER_SYSTEM,
    DEFAULT_AI2_USER_TEMPLATE,
    DEFAULT_TYPE24_EXTRAS,
    build_prompt_pack,
    default_prompt_values,
    default_system_prompt_for_type,
    looks_japanese_prompt,
    merge_type_prompts,
    normalize_production_type,
)
from ai_agent.v2.section_rules import (
    dynamic_section_rule,
    empty_prompt_sections_catalog,
    prompt_sections_from_blueprint,
)


def prompt_page_key(page: dict[str, Any]) -> str:
    slug = str(page.get("slug") or page.get("id") or "page")
    ptype = str(page.get("type") or "")
    if ptype in {"top_satellite", "top"} or slug == "home":
        return "top"
    mapping = {
        "コンセプト": "concept",
        "サービス": "service",
        "メニュー (総合)": "menu",
        "よくある質問": "faq",
        "スタッフ (代表挨拶・代表のみ)": "greeting",
        "スタッフ (複数スタッフ・詳細有り)": "staff",
        "access": "access",
        "contact": "contact",
        "blog": "blog",
        "seo": "seo",
    }
    if slug in mapping.values():
        return slug
    return mapping.get(ptype, slug)


def section_ids_for_page(page: dict[str, Any]) -> list[str]:
    return [
        str(sec.get("id") or "")
        for sec in (page.get("sections") or [])
        if isinstance(sec, dict) and str(sec.get("id") or "")
    ]


def json_example_for_page(page: dict[str, Any]) -> str:
    """Example AI-2 JSON — nested objects for content-block sections."""
    from ai_agent.v2.page_catalog import nested_fields_for_section

    parts: list[str] = []
    for sec in page.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        sid = str(sec.get("id") or "").strip()
        if not sid:
            continue
        fields = nested_fields_for_section(sec)
        if fields:
            inner = ", ".join(f'"{f}": ""' for f in fields)
            parts.append(f'"{sid}": {{{inner}}}')
        else:
            parts.append(f'"{sid}": ""')
    return '{"sections": {' + ", ".join(parts) + "}}"


def format_v2_page_rules(
    page: dict[str, Any],
    hearing: dict[str, Any] | None = None,
    *,
    type24_extras: str | None = None,
) -> str:
    """Prompt block for one page — rules come from blueprint sections (dynamic)."""
    from ai_agent.v2.page_catalog import nested_fields_for_section

    label = str(page.get("nav_label") or page.get("slug") or "page")
    lines = [
        f"ページ: {label} ({page.get('type') or ''})",
        "出力JSONキー: sections (object) — 各キーは section id。",
        "値は日本語文字列、または nested object（fields がある section: "
        "例 top_catchphrase/concept_catchphrase={catchphrase…}, "
        "point_N={title,description}, service_N={title,description}）。",
        "セクション名は STRUCTURE 用語を使う（top_catchphrase / lead / point_N）。"
        " layout語の hero は使わない。Markdown禁止。無い情報は空文字/空object。",
    ]
    if hearing and str(hearing.get("production_type") or "") in {"type3", "type4", "type1"}:
        try:
            from ai_agent.v2.site_category import site_brief_lines

            lines.extend(site_brief_lines(hearing))
        except Exception:
            pass
    if page.get("leave_blank"):
        lines.append(
            "重要: このページはヒアリング指示により全section id を空文字にする。"
            " 文案・料金表・Q&A を書かない。"
        )
    if hearing and str(hearing.get("production_type") or "") in {"type2", "type4"}:
        extras = (type24_extras or "").strip() or DEFAULT_TYPE24_EXTRAS.strip()
        if extras:
            lines.append(extras)
        project = hearing.get("project") or {}
        copy_pol = str(project.get("existing_site_copy") or "").strip()
        if "参考にしない" in copy_pol:
            lines.append("重要: 既存サイト文言は参考にしない — ヒアリング事実のみで新規執筆。")
        top_note = str(hearing.get("top_inherit_note") or "").strip()
        if str(page.get("slug") or "") == "home" and top_note:
            lines.append(f"TOP方針: {top_note}")
        exist = str(page.get("existing_url") or "").strip()
        if exist:
            lines.append(f"既存ページURL（構成参考のみ）: {exist}")
    ref = str(page.get("reference_url") or "").strip()
    if ref:
        lines.append(f"参考URL（事実参照。URL自体を本文に書かない）: {ref}")
        if str(page.get("slug") or "") == "faq" or "質問" in str(page.get("type") or ""):
            if page.get("faq_items_blank"):
                lines.append(
                    "FAQ: ヒアリングにQ&A本文なし — faq_items / faq_list / items 等の本文ブロックは空文字。"
                    "参考URLの内容を推測・創作して埋めない。hero/ctaでFAQが揃っているように書かない。"
                )
            else:
                lines.append("FAQ: 参考URLの内容をヒアリング範囲でリライトし、FAQ本文を空にしない。")
    overview = str(page.get("seo_overview") or "").strip()
    if overview:
        lines.append(f"SEOページ概要: {overview}")
    if str(page.get("type") or "") == "seo":
        primary = str(page.get("seo_primary_keyword") or "").strip()
        lines.append(
            "UNIQUE LANDING COPY: このSEOページ専用の書き出し。"
            "TOP/他SEOと同じ社名・由来オープニングの使い回し禁止。"
            "禁止: 「太陽さん」「名前になりました」「天気と付き合う仕事」などコンセプト定型の再利用。"
            "概要・主角度に合わせて差別化する。"
        )
        if primary:
            lines.append(f"主角度（冒頭1文目に含める）: {primary}")
        siblings = [str(s).strip() for s in (page.get("seo_sibling_primaries") or []) if str(s).strip()]
        if siblings:
            lines.append("他SEO主角度と書き出しを揃えない: " + "、".join(siblings[:8]))
    if page.get("force_blank_copy"):
        lines.append(
            "重要: "
            + str(page.get("force_blank_reason") or "事実不足のため全section空文字。創作禁止。")
        )
    if page.get("faq_items_blank"):
        lines.append(
            "重要: "
            + str(page.get("faq_blank_reason") or "faq_items は空文字。FAQの創作禁止。")
        )
    if hearing:
        try:
            from ai_agent.v2.site_analyzer import structure_hint_lines

            for hint in structure_hint_lines(hearing, page):
                lines.append(hint)
        except Exception:
            pass
    tag_kw = ""
    source = page.get("source") if isinstance(page.get("source"), dict) else {}
    n = source.get("n")
    if str(page.get("type") or "") == "tag":
        lines.append("ページ種別: タグキーワード用ランディング（短文SEO）。")
        lines.append(
            "UNIQUE LANDING COPY: 主キーワードから書き始める。社名由来の定型オープニング禁止。"
        )
        tags = (hearing or {}).get("tag_keywords") or []
        tag_kw = str(page.get("tag_keyword") or "").strip()
        if not tag_kw and isinstance(n, int) and 0 < n <= len(tags):
            tag_kw = str(tags[n - 1])
        if tag_kw:
            lines.append(f"主キーワード: {tag_kw}")
        instr = str(page.get("tag_instruction") or "").strip()
        body = str(page.get("tag_body") or "").strip()
        if body:
            lines.append(f"ヒアリング内容: {body}")
        if instr and instr not in {"おまかせ", "普通", "なし"}:
            lines.append(f"ヒアリング指示: {instr}")
        else:
            lines.append("指示: おまかせ → 主キーワードと店の事実だけで短文作成。料金・実績の創作禁止。")
        lines.append("各ブロックは役割どおり。他タグ語を混ぜない。")
    else:
        seeds = page.get("content_seeds") or []
        if seeds:
            lines.append("項目内容シード: " + " | ".join(str(s) for s in seeds))

    if hearing:
        wg = hearing.get("writing_guidance") or {}
        wg_lines = []
        for key, hdr in (
            ("writing_notes", "ライティング備考"),
            ("remarks", "備考"),
            ("selling_points", "売り"),
            ("atmosphere", "雰囲気"),
            ("reservation_methods", "予約方法"),
            ("ng_tone", "NG表現"),
        ):
            val = str(wg.get(key) or "").strip()
            if val and str(page.get("type") or "") in {"top_satellite", "seo", "tag", "コンセプト"}:
                wg_lines.append(f"{hdr}: {val[:400]}")
        if wg_lines:
            lines.extend(wg_lines[:4])

    sections = page.get("sections") or []
    for i, sec in enumerate(sections, start=1):
        if not isinstance(sec, dict):
            continue
        rule = str(sec.get("rule") or "").strip()
        if not rule:
            rule = dynamic_section_rule(sec, page, hearing)
        fields = nested_fields_for_section(sec)
        shape = f" nested={{{','.join(fields)}}}" if fields else ""
        lines.append(
            f"{i}. [{sec.get('id')}] {sec.get('label')} ({sec.get('mode')}{shape}): {rule}"
        )
    ids = section_ids_for_page(page)
    if ids:
        lines.append("必須 section id: " + ", ".join(ids))
        lines.append("出力例（この形のみ）: " + json_example_for_page(page))
    return SHARED_PAGE_RULES + "\n\n" + "\n".join(lines)


def default_satellite_system_prompt() -> str:
    return default_system_prompt_for_type("type3")


def default_planner_system_prompt() -> str:
    return DEFAULT_AI1_PLANNER_SYSTEM.strip()


def default_type24_extras_prompt() -> str:
    return DEFAULT_TYPE24_EXTRAS.strip()


def is_standard_site_system_prompt(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return "body_paragraphs" in t or "必ず6段落" in t or "heading, lead" in t


def is_legacy_jp_satellite_system_prompt(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "TYPE FOCUS" in t or "You are a Japanese website copywriter for BBS" in t:
        return False
    return (
        "あなたは日本の中小事業者向け" in t
        or ("出力JSONキー: sections" in t and "一字一句の意味を変えずに使う" in t)
    )


def default_satellite_user_template() -> str:
    return DEFAULT_AI2_USER_TEMPLATE.strip()


def is_standard_site_user_template(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    markers = (
        "body_paragraphs",
        "必ず6要素",
        "ページ: top",
        "slugは英数字",
        "headingは18",
    )
    return any(m in t for m in markers)


def is_legacy_jp_satellite_user_template(text: str) -> bool:
    t = (text or "").strip()
    if "Following the permitted facts" in t:
        return False
    return "各 section id ごとの日本語文案" in t and "{page_rules}" in t


def apply_satellite_lab_config(out: dict[str, Any]) -> dict[str, Any]:
    """Satellite lab config — separate English system prompt per Type 1–4."""
    out["prompt_sections"] = empty_prompt_sections_catalog()
    defaults = default_prompt_values()
    sys = str(out.get("system_prompt") or "")
    user = str(out.get("user_prompt_template") or "")
    if (
        is_standard_site_system_prompt(sys)
        or is_legacy_jp_satellite_system_prompt(sys)
        or looks_japanese_prompt(sys)
    ):
        out["system_prompt"] = defaults["system_prompt"]
    if (
        is_standard_site_user_template(user)
        or is_legacy_jp_satellite_user_template(user)
        or looks_japanese_prompt(user)
    ):
        out["user_prompt_template"] = defaults["user_prompt_template"]
    out["type_prompts"] = merge_type_prompts(out)
    # Keep flat fields in sync with type3 for older UI/clients.
    out["system_prompt"] = out["type_prompts"]["type3"]["system_prompt"]
    out["planner_system_prompt"] = out["type_prompts"]["type3"]["planner_system_prompt"]
    out["type24_extras_prompt"] = defaults.get("type24_extras_prompt") or DEFAULT_TYPE24_EXTRAS
    out["prompt_pack"] = build_prompt_pack(out)
    out["lab_mode"] = "satellite"
    return out


def resolve_satellite_write_prompts(
    cfg: dict[str, Any],
    *,
    production_type: str | None = None,
) -> tuple[str, str]:
    """AI-2 prompts for the hearing's production type (not shared across types)."""
    merged = dict(cfg or {})
    apply_satellite_lab_config(merged)
    tid = normalize_production_type(production_type)
    slot = (merged.get("type_prompts") or {}).get(tid) or {}
    system = str(slot.get("system_prompt") or "").strip() or default_system_prompt_for_type(tid)
    user = str(slot.get("user_prompt_template") or "").strip()
    if not user or looks_japanese_prompt(user) or "{page_rules}" not in user:
        # Fall back to type-specific default — never a shared cross-type template.
        from ai_agent.v2.prompt_packs import default_ai2_user_for_type

        user = default_ai2_user_for_type(tid)
    return system, user


def resolve_satellite_planner_prompt(
    cfg: dict[str, Any],
    *,
    production_type: str | None = None,
) -> str:
    """AI-1 system prompt for the hearing's production type (not shared across types)."""
    merged = dict(cfg or {})
    apply_satellite_lab_config(merged)
    tid = normalize_production_type(production_type)
    slot = (merged.get("type_prompts") or {}).get(tid) or {}
    planner = str(slot.get("planner_system_prompt") or "").strip()
    if not planner:
        from ai_agent.v2.prompt_packs import default_ai1_planner_for_type

        planner = default_ai1_planner_for_type(tid)
    return planner


def resolve_type24_extras(cfg: dict[str, Any]) -> str:
    merged = dict(cfg or {})
    apply_satellite_lab_config(merged)
    return str(merged.get("type24_extras_prompt") or "").strip() or default_type24_extras_prompt()


def prompt_sections_catalog_v2(blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    """UI catalog: from blueprint when available, otherwise empty pending state."""
    if blueprint and (blueprint.get("pages") or blueprint.get("seo_pages")):
        return prompt_sections_from_blueprint(blueprint)
    return empty_prompt_sections_catalog()
