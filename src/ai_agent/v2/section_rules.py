"""Dynamic section rules for satellite lab — derived from hearing + blueprint, not fixed checklists."""

from __future__ import annotations

from typing import Any

MODE_INSTRUCTIONS: dict[str, str] = {
    "generate": "ヒアリング事実のみを使い、このブロック用の日本語文案を書く。無い情報は空文字。",
    "facts": "ヒアリングの名称・料金・住所・時間等を正確に記載。創作・推測禁止。",
    "expand": "項目内容シードを自然な日本語に展開。未記載の設備・効果は足さない。",
    "shell": "一覧・導入テキストのみ。個別記事・下層ページは作らない。",
}

SATELLITE_TOP_MODES: dict[str, str] = {
    "hero": "地域・サービス訴求。重点ワードと店名を反映。",
    "lead": "コンセプト要約と重点ワード。",
    "services_teaser": "サービス概要（ヒアリング項目のみ）。",
    "cta": "問い合わせ・見積・予約導線。",
}

SEO_PART_BY_SECTION: dict[str, str] = {
    "intro": "冒頭",
    "point1": "推1",
    "point2": "推2",
    "summary": "まとめ",
}

TAG_SECTION_ROLES: dict[str, str] = {
    "intro": "タグキーワードの導入（何のページか・誰向けか）。",
    "point1": "タグキーワードの訴求ポイント1（店の強み・対応範囲を事実のみ）。",
    "point2": "タグキーワードの訴求ポイント2（別角度。重複しない）。",
    "summary": "まとめ＋問い合わせ・見積への短い誘導。",
}

OMACASE_HINTS = frozenset({"", "おまかせ", "普通", "なし", "-", "—", "ー"})


def _is_omacase(value: str) -> bool:
    return str(value or "").strip() in OMACASE_HINTS


def _tag_keyword(page: dict[str, Any], hearing: dict[str, Any] | None = None) -> str:
    kw = str(page.get("tag_keyword") or "").strip()
    if kw:
        return kw
    seeds = page.get("content_seeds") or []
    if seeds:
        return str(seeds[0]).strip()
    source = page.get("source") if isinstance(page.get("source"), dict) else {}
    n = source.get("n")
    if hearing and isinstance(n, int):
        tags = hearing.get("tag_keywords") or []
        if 0 < n <= len(tags):
            return str(tags[n - 1]).strip()
    return ""


def _tag_section_rule(
    section: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any] | None = None,
) -> str:
    """Short keyword-first rules for tag landing pages (hearing タグワード + 指示/内容)."""
    sid = str(section.get("id") or "")
    kw = _tag_keyword(page, hearing)
    role = TAG_SECTION_ROLES.get(sid, "タグキーワード向けの短文。")
    parts = [f"役割: {role}"]
    if kw:
        parts.append(f"主キーワード: {kw}（この語を自然に含める）")
    else:
        parts.append("主キーワード未設定 — 空文字可")

    instr = str(page.get("tag_instruction") or "").strip()
    body = str(page.get("tag_body") or "").strip()
    if body:
        parts.append(f"ヒアリング内容: {body[:240]}")
    if instr and not _is_omacase(instr):
        parts.append(f"ヒアリング指示: {instr[:200]}")
    elif _is_omacase(instr) or not instr:
        parts.append("指示: おまかせ → ヒアリング事実の範囲で自由に短文作成可。創作の料金・実績禁止。")

    if hearing:
        focus = [str(k).strip() for k in (hearing.get("focus_keywords") or []) if str(k).strip()]
        if focus:
            parts.append("関連重点ワード（必要なら1語まで）: " + "、".join(focus[:5]))
        store = hearing.get("store") or {}
        project = hearing.get("project") or {}
        name = str(project.get("business_name") or store.get("name") or "").strip()
        area = str(project.get("area") or "").strip()
        if name:
            parts.append(f"店名: {name}")
        if area:
            parts.append(f"エリア: {area}")

    parts.append("出力: 日本語2〜5文。他タグ語・他ページの話を混ぜない。無い情報は空文字。")
    return " ".join(parts)


def _seo_section_hints(page: dict[str, Any], section_id: str) -> list[str]:
    """Hearing SEO page 指示/内容 for one blueprint section."""
    part = SEO_PART_BY_SECTION.get(section_id)
    if not part:
        return []
    seo_sections = page.get("seo_sections") if isinstance(page.get("seo_sections"), dict) else {}
    block = seo_sections.get(part) if isinstance(seo_sections.get(part), dict) else {}
    hints: list[str] = []
    instr = str(block.get("指示") or "").strip()
    body = str(block.get("内容") or "").strip()
    if instr:
        hints.append(f"SEO{part}指示: {instr}")
    if body:
        hints.append(f"SEO{part}内容: {body}")
    return hints


def _page_directive_hints(page: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    if page.get("leave_blank"):
        reason = str(page.get("leave_blank_reason") or "ヒアリング指示")
        hints.append(f"重要: 全section id は空文字のみ（{reason}）")
    ref = str(page.get("reference_url") or "").strip()
    if ref:
        note = str(page.get("reference_note") or "参考URL")
        hints.append(f"{note}: {ref}")
    overview = str(page.get("seo_overview") or "").strip()
    if overview:
        hints.append(f"SEO概要: {overview}")
    # Tag body/instruction are handled in _tag_section_rule (avoid double dump).
    if str(page.get("type") or "") != "tag":
        tag_body = str(page.get("tag_body") or "").strip()
        if tag_body:
            hints.append(f"タグページ内容: {tag_body}")
    push = page.get("writing_push_points")
    if isinstance(push, list) and push:
        hints.append(
            "必須プッシュ文言（短語も含め本文に必ず含める。創作禁止・言い換え可だが語は残す）: "
            + " / ".join(str(x) for x in push[:6])
        )
    return hints


def dynamic_section_rule(
    section: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any] | None = None,
) -> str:
    """Build AI rule text from section mode, page seeds, and hearing source fields."""
    if str(page.get("type") or "") == "tag":
        return _tag_section_rule(section, page, hearing)

    sid = str(section.get("id") or "")
    mode = str(section.get("mode") or "generate")
    parts: list[str] = []

    if str(page.get("type") or "") == "top_satellite" and sid in SATELLITE_TOP_MODES:
        parts.append(SATELLITE_TOP_MODES[sid])
    else:
        parts.append(MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["generate"]))

    seeds = [str(s).strip() for s in (page.get("content_seeds") or []) if str(s).strip()]
    if seeds:
        preview = " | ".join(seeds[:8])
        if len(seeds) > 8:
            preview += " …"
        parts.append(f"項目内容: {preview}")

    source = page.get("source") if isinstance(page.get("source"), dict) else {}
    fields = [str(f).strip() for f in (source.get("fields") or []) if str(f).strip()]
    if fields:
        parts.append(f"ソース列: {', '.join(fields[:6])}")

    if hearing:
        project = hearing.get("project") or {}
        ptype = str(hearing.get("production_type") or "")
        page_type = str(page.get("type") or "")
        focus = hearing.get("focus_keywords") or []
        if focus and page_type in {"top_satellite", "top", "seo"}:
            parts.append("重点ワード: " + "、".join(str(k) for k in focus[:5]))

        wg = hearing.get("writing_guidance") or {}
        if page_type in {"top_satellite", "top"}:
            for key, label in (
                ("selling_points", "売り"),
                ("atmosphere", "雰囲気"),
                ("cv_destination", "CV先"),
                ("ng_tone", "NG表現"),
            ):
                val = str(wg.get(key) or "").strip()
                if val:
                    parts.append(f"{label}: {val[:200]}")

        # Type 2 / Type 4 renewal constraints from hearing columns
        if ptype in {"type2", "type4"}:
            copy_pol = str(project.get("existing_site_copy") or "").strip()
            if "参考にしない" in copy_pol:
                parts.append(
                    "重要: 既存サイト文言は参考にしない — ヒアリング事実のみで新規執筆。"
                    "既存ページの文章をコピー・模倣しない。"
                )
            top_note = str(hearing.get("top_inherit_note") or "").strip()
            if str(page.get("slug") or "") == "home" and (
                "しない" in top_note or "非踏襲" in top_note or not (hearing.get("flags") or {}).get("top_inherit")
            ):
                if top_note:
                    parts.append(
                        f"重要: TOP踏襲={top_note} — 旧TOPの構成・文言を引き継がない。"
                        "重点ワードと店舗事実で新規TOPを書く。"
                    )
            color_pol = str(project.get("existing_site_colors") or "").strip()
            if color_pol and str(page.get("slug") or "") == "home":
                parts.append(f"既存サイト色味方針: {color_pol}（文章には色コードを書かない）")
            exist_url = str(page.get("existing_url") or project.get("existing_url") or "").strip()
            if exist_url and (
                str((page.get("source") or {}).get("kind") or "") == "existing_page"
                or str(page.get("slug") or "") == "home"
            ):
                parts.append(
                    f"リニューアル対象ページURL（構成参考のみ・文言コピー禁止）: {exist_url}"
                )

    parts.extend(_seo_section_hints(page, sid))

    # FAQ with hearing reference URL: require Q&A rewrite (do not leave items blank).
    if str(page.get("type") or "") in {"よくある質問", "faq"} or str(page.get("slug") or "") == "faq":
        ref = str(page.get("reference_url") or "").strip()
        if ref and sid in {"items", "hero", "cta"}:
            parts.append(
                "既存FAQをヒアリング事実の範囲でリライトして埋める。"
                "Q&Aが分かる場合は items に質問と回答を書く。URL自体は本文に書かない。"
            )

    label = str(section.get("label") or sid)
    if label:
        parts.insert(0, f"ブロック: {label}")

    return " ".join(p for p in parts if p).strip()


def enrich_page_sections(page: dict[str, Any], hearing: dict[str, Any] | None = None) -> None:
    """Attach dynamic rules to each section on a blueprint page (in place)."""
    page_hints = _page_directive_hints(page)
    if page.get("leave_blank"):
        page["write_mode"] = "blank"

    out: list[dict[str, Any]] = []
    for sec in page.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        row = dict(sec)
        if page.get("leave_blank"):
            row["mode"] = "blank"
            row["rule"] = (
                (page_hints[0] if page_hints else "全section空文字")
                + " 創作禁止。"
            )
        else:
            row["rule"] = dynamic_section_rule(row, page, hearing)
            if page_hints:
                row["rule"] = row["rule"] + " " + " ".join(page_hints)
        out.append(row)
    page["sections"] = out


def prompt_sections_from_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Build Advanced prompt tabs from AI-1 blueprint pages (satellite hearing)."""
    tabs: list[dict[str, Any]] = []

    def add_page_tab(page: dict[str, Any], *, group: str = "page") -> None:
        if not isinstance(page, dict):
            return
        slug = str(page.get("slug") or page.get("id") or "page")
        sections = page.get("sections") or []
        if not sections:
            return
        modes = {str(s.get("mode") or "") for s in sections if isinstance(s, dict)}
        items = []
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            items.append(
                {
                    "id": str(sec.get("id") or ""),
                    "label": str(sec.get("label") or sec.get("id") or ""),
                    "web": str(sec.get("label") or ""),
                    "rule": str(sec.get("rule") or ""),
                    "mode": str(sec.get("mode") or ""),
                }
            )
        ptype = str(page.get("type") or "")
        label = str(page.get("nav_label") or slug)
        if group == "tag":
            kw = str(page.get("tag_keyword") or (page.get("content_seeds") or [""])[0] or "").strip()
            n = (page.get("source") or {}).get("n") if isinstance(page.get("source"), dict) else None
            label = f"{kw or label} (tag{n or ''})"
            description = (
                f"タグキーワード「{kw or '未設定'}」のランディング · {len(items)}ブロック"
                + (f" · 指示: {str(page.get('tag_instruction') or 'おまかせ')[:40]}" if page.get("tag_instruction") is not None else "")
            )
        elif group == "seo":
            label = f"{label} (seo)"
            description = f"SEOページ · {len(items)}ブロック from hearing"
        else:
            description = (
                f"{ptype} · {len(items)} blocks from this hearing"
                + (f" · seeds: {len(page.get('content_seeds') or [])}" if page.get("content_seeds") else "")
            )
        tabs.append(
            {
                "id": slug,
                "label": label,
                "web_path": "/" if slug == "home" else f"/{slug}/",
                "description": description,
                "items": items,
                "shell": modes == {"shell"},
                "dynamic": True,
                "group": "nav" if group == "page" else group,
            }
        )

    for page in blueprint.get("pages") or []:
        add_page_tab(page, group="page")
    for page in blueprint.get("seo_pages") or []:
        add_page_tab(page, group="seo")
    for page in blueprint.get("tag_pages") or []:
        add_page_tab(page, group="tag")

    return {
        "dynamic": True,
        "source": "blueprint",
        "production_type": blueprint.get("production_type"),
        "site_name": blueprint.get("site_name"),
        "tabs": tabs,
    }


def empty_prompt_sections_catalog() -> dict[str, Any]:
    """Config step before AI-1 — no static page rules."""
    return {
        "dynamic": True,
        "source": "pending",
        "tabs": [],
        "hint": "Run AI-1 Planner after loading a Sateraito hearing CSV. Section rules are built from that hearing.",
    }
