"""BBS standard page-type → section checklist (clone template for Type 1 新規).

These are the section blocks AI-2 will fill. AI-1 picks pages from the hearing
sheet and attaches the matching checklist per page type.
"""

from __future__ import annotations

from typing import Any


def _sec(sid: str, label: str, rule: str, *, mode: str = "generate") -> dict[str, str]:
    return {"id": sid, "label": label, "rule": rule, "mode": mode}


# Canonical section order per BBS page type (template clone).
PAGE_TYPE_SECTIONS: dict[str, list[dict[str, str]]] = {
    "top_satellite": [
        _sec("hero", "Satellite hero", "地域・サービス訴求。重点ワード反映。", mode="generate"),
        _sec("lead", "Lead points", "コンセプト要約＋重点ワード。", mode="expand"),
        _sec("services_teaser", "Service teaser", "サービス概要（ hearing 項目のみ）。", mode="facts"),
        _sec("cta", "Contact CTA", "問い合わせ・見積導線。", mode="generate"),
    ],
    "top": [
        _sec("hero", "Hero", "店名・キャッチ・CTA。ヒアリング事実のみ。", mode="generate"),
        _sec("about", "About", "当店について。コンセプト要約。", mode="generate"),
        _sec("concept", "Concept", "コンセプトポイント最大3。", mode="generate"),
        _sec("menu_preview", "Menu preview", "メニュー名・時間・料金（正確）。", mode="facts"),
        _sec("access", "Access", "駅・住所・営業・定休。", mode="facts"),
        _sec("cta", "Reservation CTA", "予約・電話。", mode="facts"),
    ],
    "コンセプト": [
        _sec("hero", "Concept hero", "導入見出し・リード。", mode="expand"),
        _sec("points", "Concept points", "項目内容1–15をポイント化。発明禁止。", mode="expand"),
        _sec("cta", "CTA", "ご予約導線。", mode="generate"),
    ],
    "サービス": [
        _sec("hero", "Service intro", "サービス全体説明。", mode="expand"),
        _sec("services", "Service blocks", "各サービス/コースブロック。", mode="expand"),
        _sec("cta", "CTA", "予約・電話。", mode="generate"),
    ],
    "メニュー (総合)": [
        _sec("hero", "Menu intro", "メニュー導入。", mode="generate"),
        _sec("items", "Price table", "name/duration/price 正確。", mode="facts"),
        _sec("notes", "Notes", "注意事項（ヒアリングのみ）。", mode="facts"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "よくある質問": [
        _sec("hero", "FAQ intro", "よくある質問導入。", mode="generate"),
        _sec("items", "Q&A", "ヒアリング事実からのみ。創作禁止。", mode="generate"),
        _sec("cta", "CTA", "お問い合わせ。", mode="generate"),
    ],
    "お客様の声": [
        _sec("hero", "Reviews intro", "お客様の声導入。", mode="generate"),
        _sec("items", "Review items", "口コミがある場合のみ。", mode="facts"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "スタッフ (代表挨拶・代表のみ)": [
        _sec("hero", "Greeting hero", "ご挨拶導入。", mode="generate"),
        _sec("message", "Greeting body", "代表挨拶本文。", mode="expand"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "スタッフ (複数スタッフ・詳細有り)": [
        _sec("hero", "Staff intro", "スタッフ紹介導入。", mode="generate"),
        _sec("items", "Staff profiles", "スタッフ情報がある場合のみ。", mode="facts"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "リクルート (総合)": [
        _sec("hero", "Recruit intro", "採用導入。", mode="generate"),
        _sec("positions", "Positions", "募集職種（ヒアリングのみ）。", mode="generate"),
        _sec("benefits", "Benefits", "待遇・魅力（ヒアリングのみ）。", mode="generate"),
        _sec("cta", "CTA", "応募・問い合わせ。", mode="generate"),
    ],
    "問い合わせ (ご予約)": [
        _sec("hero", "Contact hero", "お問い合わせ・予約導入。", mode="generate"),
        _sec("form", "Form note", "フォーム/電話案内（事実のみ）。", mode="facts"),
        _sec("cta", "CTA", "予約ボタン文案。", mode="generate"),
    ],
    "ギャラリー (施工事例：詳細ページ有)": [
        _sec("hero", "Gallery intro", "施工事例一覧導入。", mode="generate"),
        _sec("listing", "Case listing shell", "個別事例は作らない（CMS更新）。", mode="shell"),
        _sec("cta", "CTA", "見積・問い合わせ。", mode="generate"),
    ],
    "新着情報": [
        _sec("hero", "News intro", "新着情報一覧導入。", mode="shell"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "access": [
        _sec("hero", "Access intro", "アクセス導入。", mode="generate"),
        _sec("details", "Access details", "住所・駅・営業・駐車場。", mode="facts"),
        _sec("map", "Map note", "地図案内（住所がある場合）。", mode="facts"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "blog": [
        _sec("hero", "Blog listing", "ブログ一覧導入（記事は作らない）。", mode="shell"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "contact": [
        _sec("hero", "Contact", "ご予約・お問い合わせ。", mode="generate"),
        _sec("details", "Contact details", "電話・予約方法。", mode="facts"),
    ],
    "seo": [
        _sec("intro", "冒頭", "SEOページの導入。ヒアリングのSEO指示・内容を優先。", mode="generate"),
        _sec("point1", "推1", "SEO推1。ヒアリングの推1指示・内容を優先。", mode="generate"),
        _sec("point2", "推2", "SEO推2。ヒアリングの推2指示・内容を優先。", mode="generate"),
        _sec("summary", "まとめ", "SEOまとめ。ヒアリングのまとめ指示・内容を優先。", mode="generate"),
    ],
    # Tag keyword landing pages (タグワード1..10) — short SEO articles for one keyword.
    "tag": [
        _sec("intro", "冒頭", "タグキーワードの導入文。", mode="generate"),
        _sec("point1", "推1", "タグキーワードの訴求ポイント1。", mode="generate"),
        _sec("point2", "推2", "タグキーワードの訴求ポイント2。", mode="generate"),
        _sec("summary", "まとめ", "タグキーワードの締め・CTA寄りのまとめ。", mode="generate"),
    ],
    "reviews": [
        _sec("hero", "Reviews intro", "お客様の声導入。", mode="generate"),
        _sec("items", "Review items", "口コミがある場合のみ。", mode="facts"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
    "sitemap": [
        _sec("hero", "Sitemap intro", "サイトマップ導入（固定構造）。", mode="shell"),
    ],
    "privacy": [
        _sec("hero", "Privacy intro", "プライバシーポリシー導入（固定構造）。", mode="shell"),
    ],
    "column": [
        _sec("hero", "Column listing", "コラム一覧導入（記事は作らない）。", mode="shell"),
        _sec("cta", "CTA", "予約。", mode="generate"),
    ],
}


def sections_for_page_type(page_type: str) -> list[dict[str, str]]:
    key = str(page_type or "").strip()
    if key in PAGE_TYPE_SECTIONS:
        return [dict(s) for s in PAGE_TYPE_SECTIONS[key]]
    # Fallback: generic page
    return [
        _sec("hero", "Page intro", "ページ導入。ヒアリング事実のみ。", mode="generate"),
        _sec("body", "Body", "項目内容を反映。", mode="expand"),
        _sec("cta", "CTA", "予約・問い合わせ。", mode="generate"),
    ]


def catalog_for_api() -> dict[str, Any]:
    """Satellite lab: section structure templates (rules are filled dynamically per hearing)."""
    satellite_types = {
        "top_satellite",
        "コンセプト",
        "サービス",
        "メニュー (総合)",
        "よくある質問",
        "スタッフ (代表挨拶・代表のみ)",
        "access",
        "contact",
        "blog",
        "reviews",
        "sitemap",
        "privacy",
        "column",
        "seo",
    }
    from ai_agent.v2.page_catalog import PAGE_TYPE_SECTIONS

    return {
        "description": "Satellite page section structure (rules generated per hearing at AI-1).",
        "dynamic_rules": True,
        "page_types": [
            {
                "type": k,
                "sections": [
                    {"id": s["id"], "label": s["label"], "mode": s.get("mode", "generate")}
                    for s in v
                ],
            }
            for k, v in sorted(PAGE_TYPE_SECTIONS.items())
            if k in satellite_types
        ],
    }
