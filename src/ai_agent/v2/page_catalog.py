"""BBS page-type → section checklist (AI-1 structure / AI-2 nested content).

Nested content-block pattern (concept was only an EXAMPLE — apply to ALL content pages):
  "page_section": {
      "block": {"field_a": "...", "field_b": "..."},
      "item_1": {"title": "...", "description": "..."},
      "item_2": {"title": "...", "description": "..."}
  }

Do NOT use layout words like "hero" as section ids — use structure names
(top_catchphrase, lead, point_N, …). Template placement is AI-3.
"""

from __future__ import annotations

import re
from typing import Any


def _sec(
    sid: str,
    label: str,
    rule: str,
    *,
    mode: str = "generate",
    fields: list[str] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": sid, "label": label, "rule": rule, "mode": mode}
    if fields:
        row["fields"] = list(fields)
    return row


CATCHPHRASE_FIELDS = ["catchphrase", "short_description"]
TOP_CATCHPHRASE_FIELDS = ["brand_name", "catchphrase", "short_description"]
INTRO_FIELDS = ["heading", "lead"]
POINT_FIELDS = ["title", "description"]
SERVICE_ITEM_FIELDS = ["title", "description"]
FAQ_ITEM_FIELDS = ["question", "answer"]
MENU_ITEM_FIELDS = ["name", "duration", "price"]
REVIEW_ITEM_FIELDS = ["author", "body"]
STAFF_ITEM_FIELDS = ["name", "role", "message"]
GREETING_PROFILE_FIELDS = ["name", "role", "message", "career"]
LEAD_FIELDS = ["heading", "body"]
BUSINESS_INFO_FIELDS = [
    "name",
    "postal",
    "address",
    "phone",
    "hours",
    "closed",
    "payment",
    "email",
    "instagram",
]
CTA_FIELDS = ["label", "phone", "url", "line_url", "methods"]
ACCESS_DETAILS_FIELDS = [
    "station",
    "address",
    "phone",
    "hours",
    "closed",
    "payment",
    "parking",
    "map_note",
    "map_url",
]
CONTACT_DETAILS_FIELDS = [
    "phone",
    "email",
    "methods",
    "hours",
    "line_url",
    "instagram",
    "form_note",
]
SEO_BLOCK_FIELDS = ["heading", "body"]
SEO_SUMMARY_FIELDS = ["heading", "body", "cta_label"]
LISTING_INTRO_FIELDS = ["heading", "lead"]


def empty_nested_value(fields: list[str] | None) -> dict[str, str] | str:
    if not fields:
        return ""
    return {f: "" for f in fields}


def _seed_list(content_seeds: list[Any] | None) -> list[str]:
    return [str(s).strip() for s in (content_seeds or []) if str(s).strip()]


def _hearing_service_seeds(hearing: dict[str, Any] | None) -> list[str]:
    if not hearing:
        return []
    out: list[str] = []
    for slot in hearing.get("pages") or []:
        if not isinstance(slot, dict):
            continue
        if "サービス" not in str(slot.get("type") or ""):
            continue
        for item in slot.get("items") or []:
            t = str(item or "").strip()
            if t:
                out.append(t)
    return out


def _hearing_selling_seeds(hearing: dict[str, Any] | None) -> list[str]:
    """Parse 売り into title(+bracket) seeds for TOP selling_point_N.

    Hearing format is typically:
      地域密着、高品質、…、[bracket sentence1]、[bracket sentence2]
    Naive split on ・/。 breaks brackets. Pair title：sentence only when counts match;
    otherwise keep titles and bracket sentences as separate seeds (no wrong zip).
    """
    if not hearing:
        return []
    wg = hearing.get("writing_guidance") if isinstance(hearing.get("writing_guidance"), dict) else {}
    raw = str(wg.get("selling_points") or "").strip()
    if not raw:
        return []

    sentences: list[str] = []
    for m in re.finditer(r"\[([^\]]+)\]", raw):
        body = m.group(1).strip()
        if not body:
            continue
        sent = body.split("。")[0].strip()
        if sent:
            sentences.append(sent if sent.endswith("。") else sent + "。")

    head = re.sub(r"\[[^\]]*\]", "、", raw)
    titles: list[str] = []
    for part in re.split(r"[、,，]", head):
        p = part.strip(" 　・*-")
        if p:
            titles.append(p[:24])

    seeds: list[str] = []
    if titles and sentences and len(titles) == len(sentences):
        for title, desc in zip(titles, sentences):
            seeds.append(f"{title}：{desc}")
    else:
        # Bracket sentences first (rich facts), then short title labels.
        seeds.extend(sentences)
        for title in titles:
            if title not in seeds:
                seeds.append(title)
    return seeds[:8] or ([raw[:200]] if raw else [])


def nested_fields_for_section(section: dict[str, Any] | str) -> list[str] | None:
    if isinstance(section, dict):
        fields = section.get("fields")
        if isinstance(fields, list) and fields:
            return [str(f) for f in fields if str(f).strip()]
        sid = str(section.get("id") or "").strip().lower()
    else:
        sid = str(section or "").strip().lower()

    exact = {
        "concept_catchphrase": CATCHPHRASE_FIELDS,
        "top_catchphrase": TOP_CATCHPHRASE_FIELDS,
        "service_intro": INTRO_FIELDS,
        "faq_intro": INTRO_FIELDS,
        "menu_intro": INTRO_FIELDS,
        "reviews_intro": INTRO_FIELDS,
        "greeting_intro": INTRO_FIELDS,
        "staff_intro": INTRO_FIELDS,
        "access_intro": INTRO_FIELDS,
        "contact_intro": INTRO_FIELDS,
        "recruit_intro": INTRO_FIELDS,
        "gallery_intro": INTRO_FIELDS,
        "listing_intro": LISTING_INTRO_FIELDS,
        "lead": LEAD_FIELDS,
        "business_info": BUSINESS_INFO_FIELDS,
        "cta": CTA_FIELDS,
        "access_details": ACCESS_DETAILS_FIELDS,
        "contact_details": CONTACT_DETAILS_FIELDS,
        "greeting_profile": GREETING_PROFILE_FIELDS,
        "seo_intro": SEO_BLOCK_FIELDS,
        "seo_summary": SEO_SUMMARY_FIELDS,
        "tag_intro": SEO_BLOCK_FIELDS,
        "tag_summary": SEO_SUMMARY_FIELDS,
    }
    if sid in exact:
        return list(exact[sid])
    # Legacy layout id → treat as top catchphrase structure
    if sid == "hero":
        return list(TOP_CATCHPHRASE_FIELDS)

    for prefix, fields in (
        ("point_", POINT_FIELDS),
        ("service_", SERVICE_ITEM_FIELDS),
        ("service_teaser_", SERVICE_ITEM_FIELDS),
        ("selling_point_", POINT_FIELDS),
        ("faq_item_", FAQ_ITEM_FIELDS),
        ("menu_item_", MENU_ITEM_FIELDS),
        ("review_", REVIEW_ITEM_FIELDS),
        ("staff_", STAFF_ITEM_FIELDS),
        ("seo_point_", POINT_FIELDS),
        ("tag_point_", POINT_FIELDS),
        ("recruit_point_", POINT_FIELDS),
    ):
        if sid.startswith(prefix) and sid[len(prefix):].isdigit():
            return list(fields)
    return None


def _cta_sections() -> list[dict[str, Any]]:
    return [
        _sec(
            "cta",
            "CTA",
            "Nested {label, phone, url, line_url, methods}. "
            "Exact hearing facts for phone/URL/methods. "
            "label: clear inquiry action for lead_gen (無料相談・お見積りなど) — never empty when phone/LINE exist.",
            mode="facts",
            fields=list(CTA_FIELDS),
        )
    ]


def build_concept_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    seeds = _seed_list(content_seeds)
    n = min(max(len(seeds), 3), 15)
    out: list[dict[str, Any]] = [
        _sec(
            "concept_catchphrase",
            "Concept catchphrase",
            "Nested {catchphrase, short_description}. Hearing only.",
            mode="expand",
            fields=list(CATCHPHRASE_FIELDS),
        ),
    ]
    for i in range(1, n + 1):
        seed = seeds[i - 1] if i <= len(seeds) else ""
        rule = f"Nested {{title, description}} for concept point {i}. Hearing seed only."
        if seed:
            rule += f" Seed: {seed[:120]}"
        out.append(
            _sec(f"point_{i}", f"Concept point {i}", rule, mode="expand", fields=list(POINT_FIELDS))
        )
    out.append(_sec("reference_url", "Reference URL", "参考URLがあればそのまま。", mode="facts"))
    out.extend(_cta_sections())
    return out


def build_service_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    seeds = _seed_list(content_seeds)
    n = min(max(len(seeds), 1), 15)
    out: list[dict[str, Any]] = [
        _sec(
            "service_intro",
            "Service intro",
            "Nested {heading, lead}. Page intro only.",
            mode="expand",
            fields=list(INTRO_FIELDS),
        ),
    ]
    for i in range(1, n + 1):
        seed = seeds[i - 1] if i <= len(seeds) else ""
        rule = f"Nested {{title, description}} for service card {i}. No invented prices/工期."
        if seed:
            rule += f" Seed: {seed[:120]}"
        out.append(
            _sec(f"service_{i}", f"Service item {i}", rule, mode="expand", fields=list(SERVICE_ITEM_FIELDS))
        )
    out.extend(_cta_sections())
    return out


def build_faq_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    seeds = _seed_list(content_seeds)
    out: list[dict[str, Any]] = [
        _sec(
            "faq_intro",
            "FAQ intro",
            "Nested {heading, lead}. FAQ page intro only.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
    ]
    if seeds:
        for i, seed in enumerate(seeds[:15], start=1):
            out.append(
                _sec(
                    f"faq_item_{i}",
                    f"FAQ item {i}",
                    f"Nested {{question, answer}} from hearing only. Seed: {seed[:120]}",
                    mode="expand",
                    fields=list(FAQ_ITEM_FIELDS),
                )
            )
    else:
        out.append(
            _sec(
                "faq_items",
                "Q&A placeholder",
                "No hearing Q&A — leave empty. Do not invent from reference URL.",
                mode="blank",
            )
        )
    out.append(_sec("reference_url", "Reference URL", "参考URLがあればそのまま。", mode="facts"))
    out.extend(_cta_sections())
    return out


def build_menu_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    seeds = _seed_list(content_seeds)
    out: list[dict[str, Any]] = [
        _sec(
            "menu_intro",
            "Menu intro",
            "Nested {heading, lead}.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
    ]
    n = min(max(len(seeds), 1), 30) if seeds else 0
    for i in range(1, n + 1):
        seed = seeds[i - 1]
        out.append(
            _sec(
                f"menu_item_{i}",
                f"Menu item {i}",
                f"Nested {{name, duration, price}} exact from hearing. Seed: {seed[:120]}",
                mode="facts",
                fields=list(MENU_ITEM_FIELDS),
            )
        )
    if not seeds:
        out.append(
            _sec("menu_items", "Menu items", "No menu seeds — leave empty. Do not invent prices.", mode="blank")
        )
    out.append(_sec("notes", "Notes", "注意事項（ヒアリングのみ）。", mode="facts"))
    out.extend(_cta_sections())
    return out


def build_reviews_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    seeds = _seed_list(content_seeds)
    out: list[dict[str, Any]] = [
        _sec(
            "reviews_intro",
            "Reviews intro",
            "Nested {heading, lead}. Empty bodies when no real 口コミ.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
    ]
    if seeds:
        for i, seed in enumerate(seeds[:10], start=1):
            out.append(
                _sec(
                    f"review_{i}",
                    f"Review {i}",
                    f"Nested {{author, body}} from hearing 口コミ only. Seed: {seed[:120]}",
                    mode="facts",
                    fields=list(REVIEW_ITEM_FIELDS),
                )
            )
    else:
        out.append(
            _sec(
                "review_items",
                "Review items",
                "No review bodies in hearing — leave empty. Never invent reviews.",
                mode="blank",
            )
        )
    out.extend(_cta_sections())
    return out


def build_greeting_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    return [
        _sec(
            "greeting_intro",
            "Greeting intro",
            "Nested {heading, lead}. Empty when no representative facts.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
        _sec(
            "greeting_profile",
            "Greeting profile",
            "Nested {name, role, message, career}. Hearing staff/representative facts only.",
            mode="expand",
            fields=list(GREETING_PROFILE_FIELDS),
        ),
        *_cta_sections(),
    ]


def build_staff_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    seeds = _seed_list(content_seeds)
    out: list[dict[str, Any]] = [
        _sec(
            "staff_intro",
            "Staff intro",
            "Nested {heading, lead}.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
    ]
    n = min(max(len(seeds), 1), 15) if seeds else 0
    for i in range(1, n + 1):
        seed = seeds[i - 1]
        out.append(
            _sec(
                f"staff_{i}",
                f"Staff {i}",
                f"Nested {{name, role, message}} from hearing only. Seed: {seed[:120]}",
                mode="facts",
                fields=list(STAFF_ITEM_FIELDS),
            )
        )
    if not seeds:
        out.append(_sec("staff_items", "Staff items", "No staff facts — leave empty.", mode="blank"))
    out.extend(_cta_sections())
    return out


def build_access_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    return [
        _sec(
            "access_intro",
            "Access intro",
            "Nested {heading, lead}.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
        _sec(
            "access_details",
            "Access details",
            "Nested exact hearing facts {station,address,phone,hours,closed,payment,parking,map_note,map_url}. "
            "map_note = location only — never paste concept story.",
            mode="facts",
            fields=list(ACCESS_DETAILS_FIELDS),
        ),
        *_cta_sections(),
    ]


def build_contact_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    return [
        _sec(
            "contact_intro",
            "Contact intro",
            "Nested {heading, lead}.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
        _sec(
            "contact_details",
            "Contact details",
            "Nested exact hearing facts {phone,email,methods,hours,line_url,instagram,form_note}.",
            mode="facts",
            fields=list(CONTACT_DETAILS_FIELDS),
        ),
        *_cta_sections(),
    ]


def build_recruit_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    seeds = _seed_list(content_seeds)
    out: list[dict[str, Any]] = [
        _sec(
            "recruit_intro",
            "Recruit intro",
            "Nested {heading, lead}. Hearing recruit facts only.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
    ]
    n = min(max(len(seeds), 2), 8)
    for i in range(1, n + 1):
        seed = seeds[i - 1] if i <= len(seeds) else ""
        rule = f"Nested {{title, description}} recruit point {i}. Hearing only."
        if seed:
            rule += f" Seed: {seed[:120]}"
        out.append(
            _sec(f"recruit_point_{i}", f"Recruit point {i}", rule, mode="expand", fields=list(POINT_FIELDS))
        )
    out.extend(_cta_sections())
    return out


def build_gallery_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    return [
        _sec(
            "gallery_intro",
            "Gallery intro",
            "Nested {heading, lead}. Listing shell — do not invent case studies.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
        _sec("listing", "Case listing shell", "個別事例は作らない（CMS更新）。", mode="shell"),
        *_cta_sections(),
    ]


def build_listing_shell_sections(label: str = "Listing") -> list[dict[str, Any]]:
    return [
        _sec(
            "listing_intro",
            f"{label} intro",
            "Nested {heading, lead}. Listing shell only — no invented articles.",
            mode="shell",
            fields=list(LISTING_INTRO_FIELDS),
        ),
        *_cta_sections(),
    ]


def build_policy_shell_sections(label: str) -> list[dict[str, Any]]:
    return [
        _sec(
            "listing_intro",
            f"{label} intro",
            "Nested {heading, lead}. Fixed policy/sitemap shell.",
            mode="shell",
            fields=list(LISTING_INTRO_FIELDS),
        ),
    ]


def build_seo_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    return [
        _sec("keyword", "Keyword", "このSEOページの主キーワード。", mode="facts"),
        _sec(
            "seo_intro",
            "SEO intro",
            "Nested {heading, body}. UNIQUE landing — open on this page keyword/angle.",
            mode="generate",
            fields=list(SEO_BLOCK_FIELDS),
        ),
        _sec(
            "seo_point_1",
            "SEO point 1",
            "Nested {title, description}. 推1 from hearing. No brand-origin TOP reuse.",
            mode="generate",
            fields=list(POINT_FIELDS),
        ),
        _sec(
            "seo_point_2",
            "SEO point 2",
            "Nested {title, description}. 推2 different angle.",
            mode="generate",
            fields=list(POINT_FIELDS),
        ),
        _sec(
            "seo_summary",
            "SEO summary",
            "Nested {heading, body, cta_label}.",
            mode="generate",
            fields=list(SEO_SUMMARY_FIELDS),
        ),
    ]


def build_tag_sections(content_seeds: list[Any] | None = None) -> list[dict[str, Any]]:
    return [
        _sec("keyword", "Keyword", "このタグページの主キーワード。", mode="facts"),
        _sec(
            "tag_intro",
            "Tag intro",
            "Nested {heading, body}. Short keyword landing.",
            mode="generate",
            fields=list(SEO_BLOCK_FIELDS),
        ),
        _sec(
            "tag_point_1",
            "Tag point 1",
            "Nested {title, description}.",
            mode="generate",
            fields=list(POINT_FIELDS),
        ),
        _sec(
            "tag_point_2",
            "Tag point 2",
            "Nested {title, description}. Different angle.",
            mode="generate",
            fields=list(POINT_FIELDS),
        ),
        _sec(
            "tag_summary",
            "Tag summary",
            "Nested {heading, body, cta_label}.",
            mode="generate",
            fields=list(SEO_SUMMARY_FIELDS),
        ),
    ]


def build_top_satellite_sections(
    content_seeds: list[Any] | None = None,
    hearing: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    focus = _seed_list(content_seeds) or _seed_list(
        (hearing or {}).get("focus_keywords") if hearing else None
    )
    services = _hearing_service_seeds(hearing)
    selling = _hearing_selling_seeds(hearing)
    if not selling and focus:
        selling = focus[:3]

    out: list[dict[str, Any]] = [
        _sec(
            "top_catchphrase",
            "TOP catchphrase",
            "Nested {brand_name, catchphrase, short_description}. "
            "STRUCTURE block (not layout). brand_name exact; "
            "catchphrase ONE emotional phrase 15–28 Japanese chars from composed area+industry+売り "
            "(e.g. 島原半島・長崎… — not prefecture-only when hearing names a peninsula/city); "
            "short_description 1–2 sentences for name story / support (not the catchphrase). "
            "Placement/layout is AI-3 — do not invent layout fields.",
            mode="generate",
            fields=list(TOP_CATCHPHRASE_FIELDS),
        ),
        _sec(
            "lead",
            "Lead / concept teaser",
            "Nested {heading, body}. Concept teaser on TOP from hearing only.",
            mode="expand",
            fields=list(LEAD_FIELDS),
        ),
    ]
    svc_n = min(max(len(services), 1), 8)
    for i in range(1, svc_n + 1):
        seed = services[i - 1] if i <= len(services) else ""
        rule = f"Nested {{title, description}} TOP service teaser {i}."
        if seed:
            rule += f" Seed: {seed[:120]}"
        out.append(
            _sec(
                f"service_teaser_{i}",
                f"Service teaser {i}",
                rule,
                mode="facts" if seed else "expand",
                fields=list(SERVICE_ITEM_FIELDS),
            )
        )
    sell_n = min(max(len(selling), 1), 6)
    for i in range(1, sell_n + 1):
        seed = selling[i - 1] if i <= len(selling) else ""
        rule = f"Nested {{title, description}} TOP selling point {i}."
        if seed:
            rule += (
                f" Seed: {seed[:160]}. "
                "title = short benefit label; description = hearing fact sentence (売り bracket)."
            )
        out.append(
            _sec(
                f"selling_point_{i}",
                f"Selling point {i}",
                rule,
                mode="expand",
                fields=list(POINT_FIELDS),
            )
        )
    out.append(
        _sec(
            "business_info",
            "Business info",
            "Nested exact hearing facts {name,postal,address,phone,hours,closed,payment,email,instagram}.",
            mode="facts",
            fields=list(BUSINESS_INFO_FIELDS),
        )
    )
    out.extend(_cta_sections())
    return out


def build_top_standard_sections(
    content_seeds: list[Any] | None = None,
    hearing: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        _sec(
            "top_catchphrase",
            "TOP catchphrase",
            "Nested {brand_name, catchphrase, short_description}. STRUCTURE block (not layout). Hearing only.",
            mode="generate",
            fields=list(TOP_CATCHPHRASE_FIELDS),
        ),
        _sec(
            "lead",
            "About / lead",
            "Nested {heading, body}.",
            mode="expand",
            fields=list(LEAD_FIELDS),
        ),
        _sec("point_1", "Concept point 1", "Nested {title, description}.", mode="expand", fields=list(POINT_FIELDS)),
        _sec("point_2", "Concept point 2", "Nested {title, description}.", mode="expand", fields=list(POINT_FIELDS)),
        _sec("point_3", "Concept point 3", "Nested {title, description}.", mode="expand", fields=list(POINT_FIELDS)),
        *_cta_sections(),
    ]


# Defaults for catalog API — runtime builders use hearing seeds.
PAGE_TYPE_SECTIONS: dict[str, list[dict[str, Any]]] = {
    "top_satellite": build_top_satellite_sections(["重点1", "重点2", "重点3"]),
    "top": build_top_standard_sections(),
    "コンセプト": build_concept_sections(["項目内容1", "項目内容2", "項目内容3"]),
    "サービス": build_service_sections(["サービス1", "サービス2", "サービス3", "サービス4"]),
    "メニュー (総合)": build_menu_sections(),
    "よくある質問": build_faq_sections(),
    "お客様の声": build_reviews_sections(),
    "スタッフ (代表挨拶・代表のみ)": build_greeting_sections(),
    "スタッフ (複数スタッフ・詳細有り)": build_staff_sections(),
    "リクルート (総合)": build_recruit_sections(["職種", "待遇"]),
    "問い合わせ (ご予約)": build_contact_sections(),
    "ギャラリー (施工事例：詳細ページ有)": build_gallery_sections(),
    "新着情報": build_listing_shell_sections("News"),
    "access": build_access_sections(),
    "blog": build_listing_shell_sections("Blog"),
    "contact": build_contact_sections(),
    "seo": build_seo_sections(),
    "tag": build_tag_sections(),
    "reviews": build_reviews_sections(),
    "ai_blog": build_listing_shell_sections("AI blog"),
    "sitemap": build_policy_shell_sections("Sitemap"),
    "privacy": build_policy_shell_sections("Privacy"),
    "column": build_listing_shell_sections("Column"),
}


def sections_for_page_type(
    page_type: str,
    *,
    content_seeds: list[Any] | None = None,
    page: dict[str, Any] | None = None,
    hearing: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return nested content-block sections; expand from hearing seeds when given."""
    key = str(page_type or "").strip()
    seeds = content_seeds
    if seeds is None and isinstance(page, dict):
        seeds = page.get("content_seeds") or []

    builders = {
        "top_satellite": lambda: build_top_satellite_sections(seeds, hearing=hearing),
        "top": lambda: build_top_standard_sections(seeds, hearing=hearing),
        "コンセプト": lambda: build_concept_sections(seeds),
        "concept": lambda: build_concept_sections(seeds),
        "サービス": lambda: build_service_sections(seeds),
        "service": lambda: build_service_sections(seeds),
        "よくある質問": lambda: build_faq_sections(seeds),
        "faq": lambda: build_faq_sections(seeds),
        "メニュー (総合)": lambda: build_menu_sections(seeds),
        "お客様の声": lambda: build_reviews_sections(seeds),
        "reviews": lambda: build_reviews_sections(seeds),
        "スタッフ (代表挨拶・代表のみ)": lambda: build_greeting_sections(seeds),
        "スタッフ (複数スタッフ・詳細有り)": lambda: build_staff_sections(seeds),
        "リクルート (総合)": lambda: build_recruit_sections(seeds),
        "問い合わせ (ご予約)": lambda: build_contact_sections(seeds),
        "ギャラリー (施工事例：詳細ページ有)": lambda: build_gallery_sections(seeds),
        "新着情報": lambda: build_listing_shell_sections("News"),
        "access": lambda: build_access_sections(seeds),
        "blog": lambda: build_listing_shell_sections("Blog"),
        "contact": lambda: build_contact_sections(seeds),
        "seo": lambda: build_seo_sections(seeds),
        "tag": lambda: build_tag_sections(seeds),
        "ai_blog": lambda: build_listing_shell_sections("AI blog"),
        "sitemap": lambda: build_policy_shell_sections("Sitemap"),
        "privacy": lambda: build_policy_shell_sections("Privacy"),
        "column": lambda: build_listing_shell_sections("Column"),
    }
    if key in builders:
        return builders[key]()
    if key in PAGE_TYPE_SECTIONS:
        return [dict(s) for s in PAGE_TYPE_SECTIONS[key]]
    return [
        _sec(
            "page_intro",
            "Page intro",
            "Nested {heading, lead}. Hearing only.",
            mode="generate",
            fields=list(INTRO_FIELDS),
        ),
        _sec(
            "point_1",
            "Point 1",
            "Nested {title, description} from 項目内容.",
            mode="expand",
            fields=list(POINT_FIELDS),
        ),
        *_cta_sections(),
    ]


def catalog_for_api() -> dict[str, Any]:
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
    return {
        "description": "Nested content-block section structure for all pages.",
        "dynamic_rules": True,
        "page_types": [
            {
                "type": k,
                "sections": [
                    {
                        "id": s["id"],
                        "label": s["label"],
                        "mode": s.get("mode", "generate"),
                        **({"fields": s["fields"]} if s.get("fields") else {}),
                    }
                    for s in v
                ],
            }
            for k, v in sorted(PAGE_TYPE_SECTIONS.items())
            if k in satellite_types
        ],
    }
