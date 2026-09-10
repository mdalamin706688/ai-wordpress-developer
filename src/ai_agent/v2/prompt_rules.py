"""V2 satellite page section rules for AI-2 writer prompts."""

from __future__ import annotations

from typing import Any

from ai_agent.pipeline.copy_generator import SYSTEM_PROMPT
from ai_agent.pipeline.prompt_rules import SHARED_PAGE_RULES
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
    ids = section_ids_for_page(page)
    inner = ", ".join(f'"{sid}": ""' for sid in ids)
    return '{"sections": {' + inner + "}}"


def format_v2_page_rules(page: dict[str, Any], hearing: dict[str, Any] | None = None) -> str:
    """Prompt block for one page — rules come from blueprint sections (dynamic)."""
    label = str(page.get("nav_label") or page.get("slug") or "page")
    lines = [
        f"ページ: {label} ({page.get('type') or ''})",
        "出力JSONキー: sections (object) — 各キーは section id、値は日本語本文文字列。",
        "Markdown禁止。事実のみ。無い情報は空文字。",
    ]
    if page.get("leave_blank"):
        lines.append(
            "重要: このページはヒアリング指示により全section id を空文字にする。"
            " 文案・料金表・Q&A を書かない。"
        )
    if hearing and str(hearing.get("production_type") or "") in {"type2", "type4"}:
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
            lines.append("FAQ: 参考URLの内容をヒアリング範囲でリライトし、items を空にしない。")
    overview = str(page.get("seo_overview") or "").strip()
    if overview:
        lines.append(f"SEOページ概要: {overview}")
    tag_kw = ""
    source = page.get("source") if isinstance(page.get("source"), dict) else {}
    n = source.get("n")
    if str(page.get("type") or "") == "tag":
        lines.append("ページ種別: タグキーワード用ランディング（短文SEO）。")
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
        lines.append(
            f"{i}. [{sec.get('id')}] {sec.get('label')} ({sec.get('mode')}): {rule}"
        )
    ids = section_ids_for_page(page)
    if ids:
        lines.append("必須 section id: " + ", ".join(ids))
        lines.append("出力例（この形のみ）: " + json_example_for_page(page))
    return SHARED_PAGE_RULES + "\n\n" + "\n".join(lines)


def default_satellite_system_prompt() -> str:
    """Satellite lab system prompt — fact constraints + sections JSON output."""
    return (
        SYSTEM_PROMPT
        + """
- 出力JSONキー: sections (object) — 各キーは section id、値は日本語本文文字列。
- section id はページルールで指定されたキーのみ。Markdown禁止。
- 応答は JSON オブジェクト1つのみ。前置き・説明・コードフェンス禁止。
- 必ず {"sections": {"section_id": "日本語"}} 形式で返す。
"""
    )


def is_standard_site_system_prompt(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return "body_paragraphs" in t or "必ず6段落" in t or "heading, lead" in t


def default_satellite_user_template() -> str:
    """Satellite lab AI-2 template — section JSON, not standard-site copy shape."""
    return (
        "次の許可された事実とページルールに従い、各 section id ごとの日本語文案を書いてください。\n"
        "出力JSONキー: sections (object) — 各キーは section id、値は日本語本文文字列。\n"
        "Markdown禁止。ヒアリングに無い情報は空文字。未記載の話題は書かない。\n"
        "{page_rules}\n\n"
        "{hearing}"
    )


def is_standard_site_user_template(text: str) -> bool:
    """Detect shared standard-site lab template (TOP + body_paragraphs)."""
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


def apply_satellite_lab_config(out: dict[str, Any]) -> dict[str, Any]:
    """Satellite lab config overrides — no static section catalog or v1 copy template."""
    out["prompt_sections"] = empty_prompt_sections_catalog()
    if is_standard_site_system_prompt(str(out.get("system_prompt") or "")):
        out["system_prompt"] = default_satellite_system_prompt()
    if is_standard_site_user_template(str(out.get("user_prompt_template") or "")):
        out["user_prompt_template"] = default_satellite_user_template()
    out["lab_mode"] = "satellite"
    return out


def resolve_satellite_write_prompts(cfg: dict[str, Any]) -> tuple[str, str]:
    """Prompts used at AI-2 runtime (always satellite shape, not raw shared lab file)."""
    merged = dict(cfg or {})
    apply_satellite_lab_config(merged)
    system = str(merged.get("system_prompt") or "").strip() or default_satellite_system_prompt()
    user = str(merged.get("user_prompt_template") or "").strip() or default_satellite_user_template()
    return system, user


def prompt_sections_catalog_v2(blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    """UI catalog: from blueprint when available, otherwise empty pending state."""
    if blueprint and (blueprint.get("pages") or blueprint.get("seo_pages")):
        return prompt_sections_from_blueprint(blueprint)
    return empty_prompt_sections_catalog()
