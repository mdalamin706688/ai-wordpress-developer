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
    "hero_brand_name": "店名をヒアリングどおり（変更禁止）。",
    "hero_catchcopy": "短いキャッチ1フレーズ（15–28文字）。長文・社名由来ストーリー禁止。",
    "hero_subcopy": "コンセプト要約1〜2文。ヒアリング事実のみ。",
    "hero_focus_keywords": "重点ワードを1行1語。ヒアリングにある語のみ。",
    "hero_cta_label": "ヒーローCTAラベル（LINE/相談/見積など事実ベース）。",
    "hero_cta_url": "ヒーローCTA URL（LINE/予約URLがあればそのまま）。",
    "lead": "コンセプト要約と重点ワード。",
    "lead_heading": "リード見出し。",
    "lead_body": "リード本文。コンセプト・売りから構成。創作禁止。",
    "services_teaser": "サービス概要（ヒアリング項目のみ）。",
    "services_teaser_heading": "サービス見出し。",
    "services_teaser_items": "サービス名を1行ずつ。ヒアリング項目のみ。",
    "selling_points_heading": "強み・売りの見出し。",
    "selling_points_points": "売り・強みを1行ずつ。ヒアリングのみ。",
    "cta": "問い合わせ・見積・予約導線。",
    "cta_label": "CTAラベル。",
    "cta_phone": "電話番号そのまま。",
    "cta_url": "予約/問い合わせURLそのまま。",
    "cta_line_url": "LINE URLそのまま。",
    "cta_methods": "問い合わせ方法を1行ずつ。",
    "business_info_name": "会社名・店名そのまま。",
    "business_info_postal": "郵便番号をヒアリングどおり（空にしない）。",
    "business_info_address": "住所そのまま。",
    "business_info_phone": "電話番号そのまま。",
    "business_info_hours": "営業時間そのまま。",
    "business_info_closed": "定休日そのまま。",
    "business_info_payment": "支払い方法そのまま。",
    "business_info_email": "メールアドレスそのまま。",
    "business_info_instagram": "Instagram URLそのまま。",
    "map_note": "地図・所在地案内のみ。社名由来コンセプト文の流用禁止。",
    "map_url": "地図URLそのまま。",
}

SEO_PART_BY_SECTION: dict[str, str] = {
    "intro": "冒頭",
    "intro_heading": "冒頭",
    "intro_body": "冒頭",
    "seo_intro": "冒頭",
    "tag_intro": "冒頭",
    "point1": "推1",
    "point1_heading": "推1",
    "point1_body": "推1",
    "seo_point_1": "推1",
    "tag_point_1": "推1",
    "point2": "推2",
    "point2_heading": "推2",
    "point2_body": "推2",
    "seo_point_2": "推2",
    "tag_point_2": "推2",
    "summary": "まとめ",
    "summary_heading": "まとめ",
    "summary_body": "まとめ",
    "summary_cta_label": "まとめ",
    "seo_summary": "まとめ",
    "tag_summary": "まとめ",
    "keyword": "キーワード",
}

TAG_SECTION_ROLES: dict[str, str] = {
    "keyword": "このタグページの主キーワード（事実のみ）。",
    "intro": "タグキーワードの導入（何のページか・誰向けか）。",
    "intro_heading": "タグ導入見出し（主キーワードを自然に）。",
    "intro_body": "タグキーワードの導入本文（何のページか・誰向けか）。",
    "tag_intro": "タグ導入ブロック {heading, body}（主キーワードを自然に）。",
    "point1": "タグキーワードの訴求ポイント1（店の強み・対応範囲を事実のみ）。",
    "point1_heading": "推1見出し。",
    "point1_body": "タグキーワードの訴求ポイント1（店の強み・対応範囲を事実のみ）。",
    "tag_point_1": "タグ訴求ポイント1 {title, description}。",
    "point2": "タグキーワードの訴求ポイント2（別角度。重複しない）。",
    "point2_heading": "推2見出し。",
    "point2_body": "タグキーワードの訴求ポイント2（別角度。重複しない）。",
    "tag_point_2": "タグ訴求ポイント2 {title, description}。",
    "summary": "まとめ＋問い合わせ・見積への短い誘導。",
    "summary_heading": "まとめ見出し。",
    "summary_body": "まとめ＋問い合わせ・見積への短い誘導。",
    "summary_cta_label": "まとめCTAラベル。",
    "tag_summary": "まとめブロック {heading, body, cta_label}。",
}

OMACASE_HINTS = frozenset({"", "おまかせ", "普通", "なし", "-", "—", "ー"})
_REVIEW_FLAG_ONLY = frozenset({"表示する", "表示", "あり", "有", "yes", "true", "1"})
_REVIEW_NEGATIVE = frozenset({"表示しない", "しない", "なし", "無し", "ない", "no", "-"})

# Q&A body section ids (AI-1 may name these faq_items / items / faq_list / …)
FAQ_QA_SECTION_IDS = frozenset(
    {
        "faq_items",
        "items",
        "faq_list",
        "list",
        "faq_body",
        "faq_qa",
        "qa",
        "questions",
        "faq_questions",
        "faq_answers",
        "faq_content",
    }
)
FAQ_KEEP_SECTION_IDS = frozenset(
    {
        "faq_hero",
        "faq_intro",
        "hero",
        "hero_heading",
        "hero_lead",
        "faq_cta",
        "cta",
        "cta_label",
        "cta_phone",
        "cta_url",
        "reference_url",
        "faq_flow_cta",
        "contact_cta",
    }
)


def is_faq_qa_section_id(section_id: str) -> bool:
    """True for FAQ Q&A/list body blocks (blank when hearing has no FAQ items)."""
    sid = str(section_id or "").strip().lower()
    if not sid or sid in FAQ_KEEP_SECTION_IDS:
        return False
    if sid in FAQ_QA_SECTION_IDS:
        return True
    if sid.startswith("faq_item_") and sid[9:].isdigit():
        return True
    if sid.startswith("faq_") and any(
        tok in sid for tok in ("item", "list", "qa", "question", "answer", "body", "content")
    ):
        return True
    return False


def _is_omacase(value: str) -> bool:
    return str(value or "").strip() in OMACASE_HINTS


def is_review_body_text(text: str) -> bool:
    """True when 口コミ表示 cell has real review copy (not just a show/hide flag)."""
    t = str(text or "").strip()
    if not t or t in _REVIEW_FLAG_ONLY or t in _REVIEW_NEGATIVE:
        return False
    return True


def hearing_review_bodies(hearing: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in (hearing or {}).get("reviews") or []:
        if not isinstance(r, dict):
            continue
        if is_review_body_text(str(r.get("text") or "")):
            out.append(r)
    return out


def hearing_has_staff_greeting_facts(hearing: dict[str, Any] | None) -> bool:
    """True when hearing has staff/greeting content to write a greeting page."""
    hearing = hearing or {}
    for slot in hearing.get("pages") or []:
        if not isinstance(slot, dict):
            continue
        ptype = str(slot.get("type") or "")
        if "スタッフ" not in ptype and "挨拶" not in ptype:
            continue
        items = [str(x).strip() for x in (slot.get("items") or []) if str(x).strip()]
        if items:
            return True
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    for key in ("staff", "staff_name", "therapist", "greeting", "representative"):
        if str(store.get(key) or "").strip():
            return True
    prod = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    if str(prod.get("representative") or "").strip():
        return True
    wg = hearing.get("writing_guidance") if isinstance(hearing.get("writing_guidance"), dict) else {}
    if str(wg.get("greeting") or "").strip():
        return True
    return False


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

    parts.append("出力: 日本語2〜5文（見出しスロットは短い見出し1つ）。他タグ語・他ページの話を混ぜない。無い情報は空文字。")
    if sid == "keyword":
        parts = [
            "役割: このタグページの主キーワードをそのまま出力。",
            f"主キーワード: {kw}" if kw else "主キーワード未設定 — 空文字",
            "創作禁止。キーワード以外の文章は書かない。",
        ]
        return " ".join(parts)
    parts.append(
        "UNIQUE LANDING COPY: 冒頭を社名由来の定型文にしない。"
        "このタグ語（" + (kw or "主キーワード") + "）から書き始める。"
        "禁止: 「太陽さん」「名前になりました」などコンセプト由来ストーリーの再利用。"
    )
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


def _seo_section_rule(
    section: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any] | None = None,
) -> str:
    """Per-SEO-page rules — unique landing copy, not TOP brand-story reuse."""
    sid = str(section.get("id") or "")
    if sid == "keyword":
        primary = str(page.get("seo_primary_keyword") or "").strip()
        return (
            "役割: このSEOページの主キーワードをそのまま出力。"
            + (f" 主キーワード: {primary}" if primary else " 主キーワード未設定 — 空文字。")
            + " 創作禁止。キーワード以外の文章は書かない。"
        )
    part = SEO_PART_BY_SECTION.get(sid, sid)
    overview = str(page.get("seo_overview") or "").strip()
    primary = str(page.get("seo_primary_keyword") or "").strip()
    slot_hint = ""
    if sid.endswith("_heading"):
        slot_hint = "このスロットは見出しのみ（短い日本語）。"
    elif sid.endswith("_body") or sid == "summary_cta_label":
        slot_hint = "このスロットは本文/CTAラベル。"
    parts = [
        f"役割: SEOページ「{part}」ブロック。",
        slot_hint,
        "UNIQUE LANDING COPY: このSEOページ専用の書き出しにする。",
        "TOPや他SEOページと同じ社名・由来の定型オープニングを繰り返さない。",
        "禁止: 社名由来ストーリー（例: 「太陽さん」「名前になりました」「天気と付き合う仕事」などコンセプト定型）をSEOに再利用しない。",
    ]
    if primary:
        parts.append(f"このページの主角度: {primary} — 冒頭1文目に主角度を入れる。")
    siblings = [str(s).strip() for s in (page.get("seo_sibling_primaries") or []) if str(s).strip()]
    if siblings:
        parts.append("他SEOの主角度（書き出しを揃えない）: " + "、".join(siblings[:8]))
    if overview:
        parts.append(f"このページの主題・概要: {overview[:280]}")
    seeds = [str(s).strip() for s in (page.get("content_seeds") or []) if str(s).strip()]
    if seeds:
        parts.append("ページシード: " + " | ".join(seeds[:6]))
    parts.extend(_seo_section_hints(page, sid))
    if hearing:
        focus = [str(k).strip() for k in (hearing.get("focus_keywords") or []) if str(k).strip()]
        if focus:
            parts.append("使える重点ワード（このページに合うものだけ）: " + "、".join(focus[:5]))
        project = hearing.get("project") or {}
        name = str(project.get("business_name") or "").strip()
        area = str(project.get("area") or "").strip()
        if name:
            parts.append(f"店名: {name}")
        if area:
            parts.append(f"エリア: {area}")
    parts.append("出力: 日本語2〜5文。主題に直結。無い情報は空文字。他SEOと文面使い回し禁止。")
    return " ".join(parts)


def dynamic_section_rule(
    section: dict[str, Any],
    page: dict[str, Any],
    hearing: dict[str, Any] | None = None,
) -> str:
    """Build AI rule text from section mode, page seeds, and hearing source fields."""
    if str(page.get("type") or "") == "tag":
        return _tag_section_rule(section, page, hearing)
    if str(page.get("type") or "") == "seo":
        return _seo_section_rule(section, page, hearing)

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

    # Service cards: one nested {title, description} per hearing item
    if (
        (sid.startswith("service_") and sid[8:].isdigit())
        or sid in {"service_list", "services", "items"}
    ) and str(page.get("type") or "") in {
        "サービス",
        "service",
    }:
        n_svc = len(seeds) if seeds else 0
        if sid.startswith("service_") and sid[8:].isdigit():
            idx = int(sid[8:])
            seed = seeds[idx - 1] if 0 < idx <= len(seeds) else ""
            parts.append(
                "Nested object {title, description}. "
                "title=サービス名（ヒアリングどおり）、description=短い事実補足。"
                "料金・工期・塗料名・効果の創作禁止。"
                + (f" Seed: {seed[:160]}" if seed else "")
            )
        else:
            parts.append(
                "ヒアリングにあるサービス・工事内容を漏れなく列挙。"
                "各サービスを1行（「・サービス名：短い補足」形式可）。"
                "1行・1段落にまとめない。"
                + (f"行数の目安: {n_svc}行（シード数と同じ）。" if n_svc else "")
                + "補足はヒアリング事実のみ。料金・工期・塗料名・効果の創作禁止。無いサービスは足さない。"
            )

    # Concept points: nested {title, description} from 項目内容 seeds
    if sid == "concept_catchphrase" or (
        sid.startswith("point_") and sid[6:].isdigit()
    ):
        parts.append(
            "Nested content-block object. "
            "concept_catchphrase → {catchphrase, short_description}; "
            "point_N → {title, description}. "
            "Do not collapse all concept seeds into one paragraph."
        )

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

    # FAQ: never invent Q&A topics/prices when hearing has no FAQ items.
    if str(page.get("type") or "") in {"よくある質問", "faq"} or str(page.get("slug") or "") == "faq":
        ref = str(page.get("reference_url") or "").strip()
        if page.get("faq_items_blank"):
            if is_faq_qa_section_id(sid):
                parts.append(
                    "重要: このFAQ本文ブロックは空文字のみ（faq_items / faq_list / items 等）。"
                    "ヒアリングにFAQ本文がなく、参考URLの自動取得もないため Q&A 創作禁止"
                    "（工期・費用・塗料・保証・よくある疑問トピックの架空列挙禁止）。"
                    + (f" 参考URLは人手反映用: {ref}" if ref else "")
                )
            elif sid in FAQ_KEEP_SECTION_IDS or sid in {"faq_hero", "hero", "faq_cta", "cta", "faq_flow_cta"}:
                parts.append(
                    "hero/cta は店舗事実のみ。"
                    "「よく寄せられる質問をまとめています」など中身があるように書く表現禁止。"
                    "架空のFAQトピックを列挙しない。"
                    + (f" 参考URLあり（本文に書かない）: {ref}" if ref else "")
                )
        elif ref and (is_faq_qa_section_id(sid) or sid in FAQ_KEEP_SECTION_IDS):
            parts.append(
                "既存FAQをヒアリング事実の範囲でリライトして埋める。"
                "Q&Aが分かる場合は FAQ本文ブロックに「Q: … / A: …」形式で書く。URL自体は本文に書かない。"
                "ヒアリングにない工期・費用・塗料・保証は書かない。"
            )

    label = str(section.get("label") or sid)
    if label:
        parts.insert(0, f"ブロック: {label}")

    return " ".join(p for p in parts if p).strip()


def hearing_faq_items(hearing: dict[str, Any] | None) -> list[str]:
    if not hearing:
        return []
    for page in hearing.get("pages") or []:
        if not isinstance(page, dict):
            continue
        if str(page.get("type") or "") not in {"よくある質問", "faq"} and str(page.get("slug") or "") != "faq":
            continue
        return [str(x).strip() for x in (page.get("items") or []) if str(x).strip()]
    return []


def enrich_page_sections(page: dict[str, Any], hearing: dict[str, Any] | None = None) -> None:
    """Attach dynamic rules to each section on a blueprint page (in place)."""
    if hearing:
        try:
            from ai_agent.v2.site_analyzer import apply_live_structure_to_page_sections

            apply_live_structure_to_page_sections(page, hearing)
        except Exception:
            pass
    # Reviews with display flag but no real 口コミ本文 → blank all copy
    if hearing and str(page.get("slug") or "") == "reviews":
        if not hearing_review_bodies(hearing) and not page.get("force_blank_copy"):
            page["force_blank_copy"] = True
            page["force_blank_reason"] = "口コミ本文なし — 全section空文字。創作禁止。"
    # Greeting/staff page without staff facts → blank (do not invent 代表挨拶)
    ptype = str(page.get("type") or "")
    slug = str(page.get("slug") or "")
    if hearing and (
        slug in {"greeting", "staff"}
        or "スタッフ" in ptype
        or "挨拶" in ptype
    ):
        if not hearing_has_staff_greeting_facts(hearing):
            page["force_blank_copy"] = True
            page["force_blank_reason"] = (
                "スタッフ・代表挨拶の事実なし — 全section空文字。代表メッセージの創作禁止。"
            )

    # FAQ with reference URL but no hearing Q&A items → blank Q&A body sections (no invent)
    if hearing and (slug == "faq" or ptype in {"よくある質問", "faq"}):
        if not hearing_faq_items(hearing):
            page["faq_items_blank"] = True
            if page.get("reference_url"):
                page["faq_blank_reason"] = (
                    "FAQスロット空・参考URLのみ — FAQ本文(faq_items/faq_list等)空文字。URL内容の創作転記禁止。"
                )
            else:
                page["faq_blank_reason"] = "FAQ項目なし — FAQ本文空文字。創作禁止。"

    page_hints = _page_directive_hints(page)
    if page.get("leave_blank") or page.get("force_blank_copy"):
        page["write_mode"] = "blank"

    out: list[dict[str, Any]] = []
    for sec in page.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        row = dict(sec)
        sid = str(row.get("id") or "")
        if page.get("leave_blank") or page.get("force_blank_copy"):
            row["mode"] = "blank"
            reason = (
                page_hints[0]
                if page_hints
                else str(page.get("force_blank_reason") or page.get("leave_blank_reason") or "全section空文字")
            )
            row["rule"] = reason + " 創作禁止。"
        elif page.get("faq_items_blank") and is_faq_qa_section_id(sid):
            row["mode"] = "blank"
            row["rule"] = str(page.get("faq_blank_reason") or "FAQ本文空文字。創作禁止。")
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
                f"Tag keyword landing «{kw or 'unset'}» · {len(items)} blocks"
                + (f" · instruction: {str(page.get('tag_instruction') or 'おまかせ')[:40]}" if page.get("tag_instruction") is not None else "")
            )
        elif group == "seo":
            label = f"{label} (seo)"
            description = f"SEO page · {len(items)} blocks from hearing"
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
        "hint": "Run AI-1 Planner after loading a hearing CSV. Page blocks appear here for observation.",
    }
