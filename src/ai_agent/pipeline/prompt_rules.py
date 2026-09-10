"""Predefined section rules for model-site header pages (static nav only).

Header pages (kakureminoya gnav): TOP, concept, service, greeting, menu, faq,
feature, access, blog, column, reviews.

Excluded (dynamic sub pages — not generated):
- /blog/iYYYY…/ individual posts
- /feature/{topic}/ sub pages
- /column/{uuid} articles
"""

from __future__ import annotations

from typing import Any


SHARED_PAGE_RULES = """
共通ルール（必須）:
- ヒアリングにある事実だけを使う。無いことは書かない（省略）。発明しない。
- 店名・住所・駅・徒歩分・電話・営業時間・定休・料金・メニュー名・支払い・予約・駐車場は原文どおり。
- 「要ヒアリング」を公開文に入れない。missing は出力しない（システムが保持する）。
- 禁止: 完全個室、専用駐車場、経験豊富、専門スタッフ、無理な勧誘なし、最適なコース提案、必ず改善、医師監修、香りが漂う、など未記載の具体クレーム。
- です・ます調。Markdown・コードフェンス禁止。JSONオブジェクトのみ。
- WordPress は draft のみ。publish_allowed / published / human_approved を出力しない。
- ブログ記事・コラム記事・特徴の下層ページは作らない（ヘッダー固定ページのみ）。
""".strip()


TOP_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Hero", "web": "ファーストビュー（店名・キャッチ）", "rule": "brand_name・catchcopy・CTA。ヒアリングの店名とキャッチをそのまま。"},
    {"id": "about", "label": "About", "web": "About / 当店について", "rule": "コンセプト説明のみ。設備・効果の発明禁止。"},
    {"id": "concept", "label": "Concept", "web": "Concept（ポイント最大3）", "rule": "concept / target / tone から最大3点。未記載の設備を足さない。"},
    {"id": "greeting", "label": "Greeting", "web": "ご挨拶 / スタッフ", "rule": "スタッフ情報が無いときは書かない（省略）。発明しない。"},
    {"id": "menu", "label": "Menu", "web": "メニュー（料金プレビュー）", "rule": "menu の name / duration / price を全件・正確に。"},
    {"id": "access", "label": "Access", "web": "アクセス", "rule": "駅・徒歩・住所・電話・営業・定休・支払い・駐車場を省略せず。"},
    {"id": "reviews", "label": "Reviews", "web": "お客様の声", "rule": "口コミが無いときは書かない（省略）。発明しない。"},
    {"id": "reservation", "label": "Reservation", "web": "ご予約", "rule": "予約方法・電話・営業時間。CTA例: ご予約はこちら。"},
]

SERVICE_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Service intro", "web": "サービス導入（見出し＋全体説明）", "rule": "提供サービスの概要。ヒアリング事実のみ。効果効能の断定禁止。"},
    {"id": "services", "label": "Service blocks", "web": "サービス説明ブロック（メニュー各コース）", "rule": "menu 各コースに1ブロック。名前を変えない。料金は原文どおり。"},
    {"id": "reservation", "label": "Reservation", "web": "ご予約", "rule": "電話・営業時間・CTA。Menu（料金表）の役割を奪わない。"},
]

CONCEPT_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Concept hero", "web": "コンセプト導入", "rule": "concept / catchcopy から。未記載の設備・効果を足さない。"},
    {"id": "points", "label": "Concept points", "web": "コンセプトポイント", "rule": "concept / target / tone から最大3点。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "予約・電話のみ。発明禁止。"},
]

GREETING_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Greeting hero", "web": "ご挨拶導入", "rule": "スタッフ・挨拶情報が無いときは本文を書かない（省略）。"},
    {"id": "message", "label": "Message", "web": "ご挨拶本文", "rule": "ヒアリングの greeting / staff のみ。経歴の発明禁止。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "予約方法のみ。"},
]

MENU_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Menu intro", "web": "メニュー導入", "rule": "料金表の導入。効果効能の断定禁止。"},
    {"id": "items", "label": "Menu items", "web": "料金一覧", "rule": "menu の name / duration / price を全件・正確に。"},
    {"id": "notes", "label": "Notes", "web": "注意書き", "rule": "ヒアリングにある注意のみ。無いときは省略。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "予約・電話。"},
]

FAQ_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "FAQ intro", "web": "よくある質問導入", "rule": "ヒアリング事実に基づく導入のみ。"},
    {"id": "items", "label": "Q&A", "web": "質問と回答", "rule": "営業・予約・アクセス・メニュー料金などヒアリングにある事実からのみ。無い質問を作らない。最大6件。"},
    {"id": "cta", "label": "CTA", "web": "お問い合わせCTA", "rule": "電話・予約方法のみ。"},
]

FEATURE_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Feature intro", "web": "特徴導入", "rule": "concept / atmosphere / target のみ。下層トピック（瞑想等）のページは作らない。"},
    {"id": "points", "label": "Feature points", "web": "特徴ポイント", "rule": "ヒアリング事実から最大3点。効果効能の断定禁止。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "予約・電話のみ。"},
]

ACCESS_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Access intro", "web": "アクセス導入", "rule": "駅・徒歩を省略せず。"},
    {"id": "details", "label": "Access details", "web": "住所・駅・営業・駐車場", "rule": "address / station / hours / closed / parking / payment を原文どおり。"},
    {"id": "map", "label": "Map note", "web": "地図案内", "rule": "住所がある場合のみ案内。地図URLは発明しない。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "電話・予約。"},
]

REVIEWS_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Reviews intro", "web": "お客様の声導入", "rule": "口コミが無いときは本文を書かない（省略）。"},
    {"id": "items", "label": "Review items", "web": "口コミ一覧", "rule": "ヒアリングの reviews のみ。創作禁止。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "予約・電話。"},
]

BLOG_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Blog listing", "web": "ブログ一覧導入", "rule": "一覧ページの導入のみ。個別記事は作らない・発明しない。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "予約・電話。"},
]

COLUMN_SECTION_ITEMS: list[dict[str, str]] = [
    {"id": "hero", "label": "Column listing", "web": "コラム一覧導入", "rule": "一覧ページの導入のみ。個別コラムは作らない・発明しない。"},
    {"id": "cta", "label": "CTA", "web": "ご予約CTA", "rule": "予約・電話。"},
]


# Static header pages only (model-site gnav). No dynamic sub pages.
HEADER_PAGES: list[dict[str, Any]] = [
    {"id": "top", "label": "TOP", "web_path": "/", "wp_id": "home", "nav_label": "TOP", "ai": True, "items": TOP_SECTION_ITEMS},
    {"id": "concept", "label": "Concept", "web_path": "/concept/", "wp_id": "concept", "nav_label": "コンセプト", "ai": True, "items": CONCEPT_SECTION_ITEMS},
    {"id": "service", "label": "Service", "web_path": "/service/", "wp_id": "service", "nav_label": "サービス", "ai": True, "items": SERVICE_SECTION_ITEMS},
    {"id": "greeting", "label": "Greeting", "web_path": "/greeting/", "wp_id": "greeting", "nav_label": "ご挨拶", "ai": True, "optional": "staff", "items": GREETING_SECTION_ITEMS},
    {"id": "menu", "label": "Menu", "web_path": "/menu/", "wp_id": "menu", "nav_label": "メニュー", "ai": True, "items": MENU_SECTION_ITEMS},
    {"id": "faq", "label": "FAQ", "web_path": "/faq/", "wp_id": "faq", "nav_label": "よくある質問", "ai": True, "items": FAQ_SECTION_ITEMS},
    {"id": "feature", "label": "Feature", "web_path": "/feature/", "wp_id": "feature", "nav_label": "特徴", "ai": True, "items": FEATURE_SECTION_ITEMS},
    {"id": "access", "label": "Access", "web_path": "/access/", "wp_id": "access", "nav_label": "アクセス", "ai": True, "items": ACCESS_SECTION_ITEMS},
    {"id": "blog", "label": "Blog", "web_path": "/blog/", "wp_id": "blog", "nav_label": "ブログ", "ai": False, "shell": True, "items": BLOG_SECTION_ITEMS},
    {"id": "column", "label": "Column", "web_path": "/column/", "wp_id": "column", "nav_label": "コラム", "ai": False, "shell": True, "items": COLUMN_SECTION_ITEMS},
    {"id": "reviews", "label": "Reviews", "web_path": "/reviews/", "wp_id": "reviews", "nav_label": "お客様の声", "ai": True, "optional": "reviews", "items": REVIEWS_SECTION_ITEMS},
]

_PAGE_ITEMS: dict[str, list[dict[str, str]]] = {
    str(p["id"]): list(p["items"]) for p in HEADER_PAGES
}
_PAGE_META: dict[str, dict[str, Any]] = {str(p["id"]): p for p in HEADER_PAGES}


def section_items_for(page: str) -> list[dict[str, str]]:
    key = (page or "top").strip().lower()
    if key in {"home", ""}:
        key = "top"
    if key in {"services"}:
        key = "service"
    items = _PAGE_ITEMS.get(key) or TOP_SECTION_ITEMS
    return [dict(item) for item in items]


def header_page_meta(page: str) -> dict[str, Any]:
    key = (page or "top").strip().lower()
    if key in {"home", ""}:
        key = "top"
    return dict(_PAGE_META.get(key) or _PAGE_META["top"])


def header_ai_page_ids(*, hearing: dict[str, Any] | None = None) -> list[str]:
    """AI pages for one production run (static header only; skip empty optionals)."""
    hearing = hearing or {}
    out: list[str] = []
    for page in HEADER_PAGES:
        if not page.get("ai"):
            continue
        opt = page.get("optional")
        if opt == "staff":
            if not any(str(hearing.get(k) or "").strip() for k in ("staff", "staff_name", "therapist", "greeting")):
                continue
        if opt == "reviews":
            reviews = hearing.get("reviews")
            if not (isinstance(reviews, list) and reviews) and not str(hearing.get("reviews") or "").strip():
                continue
        out.append(str(page["id"]))
    return out


def prompt_sections_catalog() -> dict[str, Any]:
    """Payload for Advanced prompt UI tabs — all static header pages."""
    tabs = []
    for page in HEADER_PAGES:
        tabs.append(
            {
                "id": page["id"],
                "label": page["label"],
                "web_path": page["web_path"],
                "description": f"Production {page['label']} page for WordPress drafts.",
                "items": [dict(i) for i in page["items"]],
                "ai": bool(page.get("ai")),
                "shell": bool(page.get("shell")),
            }
        )
    return {"tabs": tabs}


def format_section_items_for_prompt(page: str) -> str:
    """Render predefined items into prompt text the writer must follow."""
    key = (page or "top").strip().lower()
    if key in {"home", ""}:
        key = "top"
    if key in {"services"}:
        key = "service"
    meta = header_page_meta(key)
    items = section_items_for(key)
    title = str(meta.get("label") or key).upper()
    slug = str(meta.get("wp_id") or key)
    lines = [
        f"ページ: {title}",
        "以下の所定セクション順に従って日本語原稿JSONを書いてください（本番WordPress下書き用の固定構成）。",
        "出力キー: title, slug, heading, lead, body_paragraphs (必ず6要素), cta, notes",
        "body_paragraphs は所定セクションの内容を反映すること（無いセクションは空にせず、省略して他段落で事実を書く）。",
        f"slug は {slug}。",
    ]
    for i, item in enumerate(items, start=1):
        lines.append(
            f"{i}. [{item['id']}] {item['label']} — {item['web']}: {item['rule']}"
        )
    if key == "top":
        lines.extend(
            [
                "title は「店名｜エリア＋業種」。",
                "heading は18〜28字。lead は2文。最寄駅は省略しない。",
                "body_paragraphs は必ず6段落。各段落3〜4文。箇条書きにしない。",
                "1: コンセプト 2: メニュー（料金正確） 3: アクセス 4: 営業・定休・支払い "
                "5: 初回・予約 6: 締め（押しつけない）。",
            ]
        )
    elif key == "service":
        lines.extend(
            [
                "title は「サービス｜店名」。",
                "Service は説明。Menu は料金表。役割を混ぜない。",
            ]
        )
    elif key == "faq":
        lines.append("FAQはヒアリングにある事実からのみ。無いQ&Aを創作しない。")
    elif key in {"blog", "column"}:
        lines.append("一覧導入のみ。個別記事・個別コラムは作らない。")
    elif key == "feature":
        lines.append("特徴の親ページのみ。瞑想・健康などの下層ページは作らない。")
    return "\n".join(lines)


def page_prompt_rules(page: str) -> str:
    return SHARED_PAGE_RULES + "\n\n" + format_section_items_for_prompt(page)


def default_lab_user_template() -> str:
    """Classic lab user prompt (UI). Page section rules are shown in tabs below and appended at generate time."""
    return (
        "次の許可された事実だけを使って、指定ページの日本語原稿を書いてください。\n"
        "ページ: top\n"
        "出力JSONキー: title, slug, heading, lead, body_paragraphs (必ず6要素), cta, notes\n"
        "titleは「店名｜エリア＋業種」。slugは英数字ハイフン。\n"
        "headingは18〜28字。キャッチコピーを活かし、看板として美しい一文。体言止め可。\n"
        "leadは2文。最寄駅はヒアリングの表記を省略せず使う。「から徒歩N分」だけで始めない。\n"
        "body_paragraphsは必ず6段落。各段落3〜4文。合計700〜950字。箇条書きにしない。\n"
        "1: コンセプトと、ヒアリングにある雰囲気だけ。2: メニュー（各コース名、時間、料金。効果効能は書かない）。\n"
        "3: 最寄駅・住所・駐車場。4: 営業時間・定休・支払い。5: 初回来店の流れと予約（電話・LINE）。6: 締め（近隣の方へ、押しつけない）。\n"
        "ctaは予約ボタン。例: ご予約はこちら。\n"
        "禁止: 許可された事実に無い料金・駅名・電話・口コミ・スタッフ名・人数・実績を書くこと。\n"
        "禁止: ヒアリングに無い個室・香りの空間・効果効能・案内約束を作ること。\n"
        "重要: 未記載の話題は本文に書かない。「要ヒアリング」をリードや本文に埋め込まない。"
        "必要な場合のみ notes に短く書く。\n"
        "{hearing}"
    )
