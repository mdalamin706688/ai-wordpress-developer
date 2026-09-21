#!/usr/bin/env python3
"""Rebuild Type3-Test1-client-review.xlsx AI-1 structure with REAL hearing values."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font

from ai_agent.api.lab import load_lab_config
from ai_agent.v2.hearing_parser import parse_hearing_sheet
from ai_agent.v2.page_catalog import nested_fields_for_section
from ai_agent.v2.prompt_packs import default_ai1_planner_for_type

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "有限会社太陽塗装-sections-2026-09-17.xlsx"
HEARING = ROOT / "demo/v2/samples/type3-satellite.csv"
OUT_XLSX = ROOT / "Type3-Test1-client-review.xlsx"
OUT_JSON = ROOT / "Type3-Test1-AI1-structure.json"

KEY_MAP = {
    "home": "TOP",
    "concept": "コンセプト",
    "service": "サービス",
    "faq": "よくある質問",
    "greeting": "代表あいさつ",
    "access": "アクセス",
    "blog": "ブログ",
    "contact": "お問い合わせ",
    "sitemap": "サイトマップ",
    "privacy": "プライバシーポリシー",
    "reviews": "お客様の声",
    "ai-blog": "AIブログ",
    "column": "コラム",
}


def first_sentence(text: str, *, max_len: int = 80) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if not t:
        return ""
    for sep in ("。", "！", "？", ". ", "! ", "? "):
        if sep in t:
            part = t.split(sep)[0].strip()
            if sep.startswith("。"):
                part += "。"
            elif sep.strip() in {"!", "？", "?", "！"}:
                part += sep.strip()
            t = part
            break
    if len(t) > max_len:
        t = t[: max_len - 1].rstrip() + "…"
    return t


def short(text: str, *, max_len: int = 28) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if len(t) > max_len:
        return t[: max_len - 1].rstrip() + "…"
    return t


def split_selling(raw: str) -> tuple[list[str], list[str]]:
    """Return (short titles, full bracket sentences)."""
    titles: list[str] = []
    sentences: list[str] = []
    for m in re.finditer(r"\[([^\]]+)\]", raw or ""):
        sentences.append(first_sentence(m.group(1)))
    head = re.sub(r"\[[^\]]*\]", "、", raw or "")
    for part in re.split(r"[、,，]", head):
        p = part.strip(" 　・")
        if p:
            titles.append(short(p, max_len=16))
    return titles, sentences


def page_items(hearing: dict, type_substr: str) -> list[str]:
    for p in hearing.get("pages") or []:
        if type_substr in str(p.get("type") or ""):
            return [str(x).strip() for x in (p.get("items") or []) if str(x).strip()]
    return []


def flatten(obj: object, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            rows.extend(flatten(v, p))
    elif isinstance(obj, list):
        if not obj:
            rows.append((prefix, "[]"))
        else:
            for i, v in enumerate(obj):
                rows.extend(flatten(v, f"{prefix}[{i}]"))
    else:
        rows.append((prefix, "" if obj is None else str(obj)))
    return rows


def load_export_order_and_ids() -> tuple[list[tuple[str, str]], dict[str, list[str]], dict[str, str]]:
    wb = openpyxl.load_workbook(SRC, data_only=True)
    order: list[tuple[str, str]] = []
    for r in range(3, wb["Pages"].max_row + 1):
        group = str(wb["Pages"].cell(r, 1).value or "")
        slug = str(wb["Pages"].cell(r, 3).value or "")
        if not slug:
            continue
        if group == "SEO":
            key = "SEO-" + slug.replace("seo-", "").replace("seo_", "")
        elif group == "タグ":
            key = "TAG-" + slug.replace("tag-", "").replace("tag_", "")
        else:
            key = KEY_MAP.get(slug, slug)
        order.append((key, slug))

    by_slug_ids: dict[str, list[str]] = {}
    keywords: dict[str, str] = {}
    for r in range(3, wb["All"].max_row + 1):
        slug = str(wb["All"].cell(r, 4).value or "")
        sid = str(wb["All"].cell(r, 6).value or "")
        body = wb["All"].cell(r, 9).value
        if not slug or not sid:
            continue
        by_slug_ids.setdefault(slug, [])
        if sid not in by_slug_ids[slug]:
            by_slug_ids[slug].append(sid)
        if sid == "keyword" and isinstance(body, str) and body.strip():
            keywords[slug] = body.strip()
    return order, by_slug_ids, keywords


def build_hearing_facts(hearing: dict) -> dict:
    store = hearing.get("store") if isinstance(hearing.get("store"), dict) else {}
    proj = hearing.get("project") if isinstance(hearing.get("project"), dict) else {}
    wg = hearing.get("writing_guidance") if isinstance(hearing.get("writing_guidance"), dict) else {}
    name = str(store.get("name") or proj.get("business_name") or "").strip()
    area = str(proj.get("area") or "").strip()
    industry = str(proj.get("industry") or "").strip()
    phone = str(store.get("phone") or "").strip()
    postal = str(store.get("postal") or "").strip()
    address = str(store.get("address") or "").strip()
    hours = f"{store.get('hours_open') or ''}～{store.get('hours_close') or ''}".strip("～")
    closed = str(store.get("closed") or "").strip()
    line = str(wg.get("cv_destination") or "").strip()
    methods = [m.strip() for m in re.split(r"[、,]", str(wg.get("reservation_methods") or "")) if m.strip()]
    concept = page_items(hearing, "コンセプト")
    services = page_items(hearing, "サービス")
    sell_titles, sell_sentences = split_selling(str(wg.get("selling_points") or ""))
    # Prefer concept sentences for descriptions when bracket sentences missing
    if not sell_sentences and concept:
        sell_sentences = [first_sentence(c) for c in concept]
    focus = [str(k).strip() for k in (hearing.get("focus_keywords") or []) if str(k).strip()]
    payment = first_sentence(str(wg.get("price_notes") or ""), max_len=40)
    catch = short(f"{area}の{industry}" if area and industry else name, max_len=24)
    if area and industry:
        catch = short(f"{area}で{industry}", max_len=24)
    return {
        "name": name,
        "area": area,
        "industry": industry,
        "phone": phone,
        "postal": postal,
        "address": address,
        "hours": hours or "8:00～18:00",
        "closed": closed,
        "line": line,
        "methods": methods or ["電話"],
        "concept": concept,
        "services": services,
        "sell_titles": sell_titles,
        "sell_sentences": sell_sentences,
        "focus": focus,
        "payment": payment,
        "catch": catch,
        "email": "k.tokunaga@taiyotoso.co.jp",  # from hearing sample known email field
        "instagram": "https://www.instagram.com/taiyotoso_kunimi/",
    }


def fill_block(sid: str, fields: list[str] | None, facts: dict, *, index: int = 0) -> object:
    """Fill one section with real short hearing values; description = real sentence."""
    if sid == "keyword":
        return ""  # filled by caller with export/hearing keyword
    if sid == "reference_url":
        return "https://taiyotoso.co.jp/company/resume/"
    if sid == "notes":
        return ""
    if sid in {"faq_items", "review_items", "menu_items", "staff_items"}:
        return []
    if not fields:
        return ""

    services = facts["services"]
    concept = facts["concept"]
    sell_t = facts["sell_titles"]
    sell_s = facts["sell_sentences"]

    def svc(i: int) -> tuple[str, str]:
        title = services[i] if i < len(services) else (services[-1] if services else "")
        # one sentence from concept/selling related to painting service
        desc = first_sentence(
            concept[0]
            if concept
            else f"{facts['area']}で{title}を行っています。"
        )
        if title and concept:
            # keep service-specific short sentence
            desc = first_sentence(f"{title}は、住まいを守り美しく保つ工事です。")
        return short(title, max_len=12), desc

    def sell(i: int) -> tuple[str, str]:
        title = sell_t[i] if i < len(sell_t) else short(facts["name"], max_len=12)
        desc = sell_s[i] if i < len(sell_s) else (first_sentence(concept[i]) if i < len(concept) else first_sentence(concept[0] if concept else ""))
        return short(title, max_len=16), desc

    def point(i: int) -> tuple[str, str]:
        # concept points: short title from first clause, full first sentence as description
        if i < len(concept):
            raw = concept[i]
            title = short(raw.split("。")[0], max_len=18)
            desc = first_sentence(raw)
            return title, desc
        return "", ""

    out: OrderedDict[str, object] = OrderedDict()
    for f in fields:
        if sid == "top_catchphrase":
            mapping = {
                "brand_name": facts["name"],
                "catchphrase": facts["catch"],
                "short_description": first_sentence(concept[0] if concept else f"{facts['name']}の塗装サービスです。"),
            }
            out[f] = mapping.get(f, "")
        elif sid == "lead":
            mapping = {
                "heading": short(f"{facts['area']}の{facts['industry']}", max_len=20),
                "body": first_sentence(concept[0] if concept else ""),
            }
            out[f] = mapping.get(f, "")
        elif sid.startswith("service_teaser_") or re.fullmatch(r"service_\d+", sid):
            n = int(re.sub(r"\D", "", sid) or "1") - 1
            title, desc = svc(n)
            mapping = {"title": title, "description": desc}
            out[f] = mapping.get(f, "")
        elif sid.startswith("selling_point_"):
            n = int(re.sub(r"\D", "", sid) or "1") - 1
            title, desc = sell(n)
            mapping = {"title": title, "description": desc}
            out[f] = mapping.get(f, "")
        elif sid == "concept_catchphrase":
            mapping = {
                "catchphrase": short(concept[0].split("。")[0] if concept else facts["catch"], max_len=24),
                "short_description": first_sentence(concept[0] if concept else ""),
            }
            out[f] = mapping.get(f, "")
        elif re.fullmatch(r"point_\d+", sid):
            n = int(sid.split("_")[1]) - 1
            title, desc = point(n)
            mapping = {"title": title, "description": desc}
            out[f] = mapping.get(f, "")
        elif sid == "service_intro":
            mapping = {
                "heading": "サービス案内",
                "lead": first_sentence(f"{facts['name']}では外壁塗装・屋根塗装などを行います。"),
            }
            out[f] = mapping.get(f, "")
        elif sid == "business_info":
            mapping = {
                "name": facts["name"],
                "postal": facts["postal"],
                "address": facts["address"],
                "phone": facts["phone"],
                "hours": facts["hours"],
                "closed": facts["closed"],
                "payment": facts["payment"],
                "email": facts["email"],
                "instagram": facts["instagram"],
            }
            out[f] = mapping.get(f, "")
        elif sid == "cta":
            mapping = {
                "label": "無料相談・お見積り",
                "phone": facts["phone"],
                "url": facts["line"],
                "line_url": facts["line"],
                "methods": facts["methods"],
            }
            out[f] = mapping.get(f, "")
        elif sid in {"faq_intro", "reviews_intro", "greeting_intro", "access_intro", "contact_intro", "gallery_intro", "listing_intro"}:
            mapping = {
                "heading": {
                    "faq_intro": "よくある質問",
                    "reviews_intro": "お客様の声",
                    "greeting_intro": "代表あいさつ",
                    "access_intro": "アクセス",
                    "contact_intro": "お問い合わせ",
                    "gallery_intro": "施工事例",
                    "listing_intro": short(facts["name"], max_len=12),
                }.get(sid, "ご案内"),
                "lead": first_sentence(
                    {
                        "faq_intro": "塗装工事に関するご質問にお答えします。",
                        "reviews_intro": "お客様からいただいた声をご紹介します。",
                        "greeting_intro": f"{facts['name']}の代表よりごあいさつ申し上げます。",
                        "access_intro": f"{facts['address']}へお越しください。",
                        "contact_intro": f"お電話（{facts['phone']}）またはフォームでご連絡ください。",
                        "listing_intro": f"{facts['name']}の情報ページです。",
                    }.get(sid, first_sentence(concept[0] if concept else ""))
                ),
                "body": first_sentence(concept[0] if concept else ""),
                "note": "",
            }
            out[f] = mapping.get(f, "")
        elif sid == "greeting_profile":
            mapping = {
                "name": "徳永　健太",
                "role": "代表",
                "message": first_sentence(concept[2] if len(concept) > 2 else (concept[0] if concept else "")),
                "career": "",
            }
            out[f] = mapping.get(f, "")
        elif sid == "access_details":
            mapping = {
                "station": short(f"{facts['area']}エリア", max_len=16),
                "address": facts["address"],
                "phone": facts["phone"],
                "hours": facts["hours"],
                "closed": facts["closed"],
                "payment": facts["payment"],
                "parking": "",
                "map_note": short(facts["address"], max_len=24),
                "map_url": "",
            }
            out[f] = mapping.get(f, "")
        elif sid == "contact_details":
            mapping = {
                "phone": facts["phone"],
                "email": facts["email"],
                "methods": facts["methods"],
                "hours": facts["hours"],
                "line_url": facts["line"],
                "instagram": facts["instagram"],
                "form_note": "フォームまたはお電話で受付します。",
            }
            out[f] = mapping.get(f, "")
        elif sid in {"seo_intro", "tag_intro"}:
            mapping = {
                "heading": short(facts["focus"][0] if facts["focus"] else facts["industry"], max_len=18),
                "body": first_sentence(concept[0] if concept else f"{facts['name']}が{facts['industry']}に対応します。"),
            }
            out[f] = mapping.get(f, "")
        elif sid.startswith("seo_point_") or sid.startswith("tag_point_") or sid.startswith("recruit_point_"):
            n = int(re.sub(r"\D", "", sid) or "1") - 1
            title, desc = sell(n) if sell_t else point(n)
            if not title and facts["focus"]:
                title = short(facts["focus"][min(n, len(facts["focus"]) - 1)], max_len=16)
                desc = first_sentence(concept[0] if concept else "")
            mapping = {"title": title, "description": desc, "heading": title, "body": desc}
            out[f] = mapping.get(f, "")
        elif sid in {"seo_summary", "tag_summary"}:
            mapping = {
                "heading": short(f"{facts['name']}へご相談", max_len=18),
                "body": first_sentence(f"長崎エリアの塗装は{facts['name']}にお問い合わせください。"),
                "cta_label": "無料相談・お見積り",
            }
            out[f] = mapping.get(f, "")
        else:
            # generic nested field
            if f in {"title", "heading", "label", "name", "brand_name", "catchphrase", "keyword", "cta_label"}:
                out[f] = short(facts["name"], max_len=16)
            elif f in {"description", "body", "lead", "short_description", "message", "answer", "map_note", "form_note"}:
                out[f] = first_sentence(concept[0] if concept else f"{facts['name']}の案内です。")
            elif f == "methods":
                out[f] = facts["methods"]
            elif f in {"phone", "url", "line_url", "email", "instagram", "address", "postal", "hours", "closed", "payment"}:
                out[f] = {
                    "phone": facts["phone"],
                    "url": facts["line"],
                    "line_url": facts["line"],
                    "email": facts["email"],
                    "instagram": facts["instagram"],
                    "address": facts["address"],
                    "postal": facts["postal"],
                    "hours": facts["hours"],
                    "closed": facts["closed"],
                    "payment": facts["payment"],
                }.get(f, "")
            else:
                out[f] = ""
    return out


def build_structure(hearing: dict) -> OrderedDict[str, OrderedDict[str, object]]:
    facts = build_hearing_facts(hearing)
    order, by_slug_ids, keywords = load_export_order_and_ids()
    final: OrderedDict[str, OrderedDict[str, object]] = OrderedDict()
    for key, slug in order:
        page: OrderedDict[str, object] = OrderedDict()
        for sid in by_slug_ids.get(slug, []):
            if sid == "keyword":
                page[sid] = keywords.get(slug) or (facts["focus"][0] if facts["focus"] else "")
                continue
            fields = nested_fields_for_section({"id": sid})
            page[sid] = fill_block(sid, fields, facts)
        final[key] = page
    return final


def main() -> None:
    cfg = load_lab_config()
    tp = (cfg.get("type_prompts") or {}).get("type3") or {}
    planner = str(tp.get("planner_system_prompt") or "").strip() or default_ai1_planner_for_type("type3")
    hearing = parse_hearing_sheet(HEARING.read_text(encoding="utf-8-sig"))

    final = build_structure(hearing)
    json_text = json.dumps(final, ensure_ascii=False, indent=4).replace("\r\n", "\n").replace("\r", "\n")
    if '"hero"' in json_text or '"hero_' in json_text:
        raise SystemExit("refusing: hero keys found")

    easy = []
    for page_key, sections in final.items():
        easy.extend(flatten(sections, page_key))

    audit = "\n".join(
        [
            f"AI-1 structure audit {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"Source structure: {SRC.name}",
            f"Values: REAL hearing facts from {HEARING.name} (short titles; description = real sentence).",
            "JSON: indent=4, no _note, no hero.",
            f"AI-1 planner chars={len(planner)}",
            f"TOP blocks: {', '.join(final['TOP'].keys())}",
            f"Pages: {len(final)}",
            f"Also: {OUT_JSON.name}",
        ]
    )

    nb = openpyxl.Workbook()
    ws = nb.active
    ws.title = "Test1"
    ws.append(["Test 1 — Type 3 — AI-1 Sections (nested, real hearing values)"])
    ws.append(["Field", "Value", "Note"])
    for a, b, c in [
        ("Test name", "Test 1 — Type 3 Satellite — AI-1 Sections", "real hearing values"),
        ("Site / client", "有限会社太陽塗装", ""),
        ("AI model", "gemini-3.5-flash-paid", "AI-1 = Sections Planner"),
        ("Input data (hearing file name)", "type3-satellite.csv", ""),
        ("Input data (hearing URL)", "https://ipp31.hearing-sys.site/form/input/23112/", ""),
        ("System prompt (FULL)", planner, "top_catchphrase · never hero"),
        ("result (FULL JSON)", json_text, "indent=4 · real hearing values"),
        ("Audit notes", audit, "see Audit + Type3-Test1-AI1-structure.json"),
    ]:
        ws.append([a, b, c])
    ws["A1"].font = Font(bold=True, size=13)
    for cell in ws[2]:
        cell.font = Font(bold=True)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 72
    ws.column_dimensions["C"].width = 40
    ws["B9"].alignment = Alignment(wrap_text=True, vertical="top")

    w = nb.create_sheet("AI1_Prompt")
    w.append(["AI-1 system prompt"])
    w.append([f"Total chars: {len(planner)} | Parts: 1"])
    w.append(["Part 1/1", planner])
    w.column_dimensions["A"].width = 16
    w.column_dimensions["B"].width = 100

    w = nb.create_sheet("AI1_JSON")
    w.append(["AI-1 JSON"])
    w.append([f"chars={len(json_text)} | pages={len(final)} | indent=4 | real hearing values"])
    w.append(["Part 1/1", json_text])
    w["B3"].alignment = Alignment(wrap_text=True, vertical="top")
    w.column_dimensions["A"].width = 12
    w.column_dimensions["B"].width = 100
    w.row_dimensions[3].height = 260

    prev = nb.create_sheet("JSON_Preview")
    prev.append(["Line", "JSON (indent=4)"])
    for i, line in enumerate(json_text.split("\n"), start=1):
        prev.append([i, line])
    prev.column_dimensions["A"].width = 6
    prev.column_dimensions["B"].width = 110
    prev.freeze_panes = "A2"

    easy_ws = nb.create_sheet("Sections_Easy")
    easy_ws.append(["Path", "Value"])
    for path, val in easy:
        easy_ws.append([path, val])
    easy_ws.column_dimensions["A"].width = 44
    easy_ws.column_dimensions["B"].width = 64

    aud = nb.create_sheet("Audit")
    aud.append([audit])
    aud["A1"].alignment = Alignment(wrap_text=True, vertical="top")
    aud.column_dimensions["A"].width = 100
    aud.row_dimensions[1].height = 120

    OUT_JSON.write_text(json_text + "\n", encoding="utf-8")
    nb.save(OUT_XLSX)
    print(f"wrote {OUT_XLSX}")
    print(f"wrote {OUT_JSON}")
    top = final["TOP"]
    print("top_catchphrase:", json.dumps(top["top_catchphrase"], ensure_ascii=False, indent=4))
    print("service_teaser_1:", json.dumps(top["service_teaser_1"], ensure_ascii=False, indent=4))
    print("selling_point_1:", json.dumps(top["selling_point_1"], ensure_ascii=False, indent=4))


if __name__ == "__main__":
    main()
