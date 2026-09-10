#!/usr/bin/env python3
"""Build production-focused client model sheet (not free vs paid)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "client_production_model_sheet.csv"

FACT_ORDER = ["shop", "station", "hours", "closed", "phone", "aromatherapy", "headspa", "price"]
FACT_LABELS = {
    "shop": "店名",
    "station": "最寄駅",
    "hours": "営業時間",
    "closed": "定休日",
    "phone": "電話",
    "aromatherapy": "アロマ",
    "headspa": "ヘッドスパ",
    "price": "価格",
}

FALLBACK_POC = {
    "glm-4.7-flash": {
        "facts_pct": "5/8 (63%)",
        "facts_score_pct": 63,
        "speed_sec": 15.0,
        "invented": 0,
        "forbidden": 0,
        "fact_marks": "×○×○×○○○",
        "status": "OK (prior run)",
        "note": "Same 8-fact test; 2026-08-19 rerun blocked by Z.AI 429",
    },
}

# Production models — ranked for Japanese hearing-sheet → homepage copy.
PRODUCTION_MODELS = [
    {
        "rank": 1,
        "model": "Claude Sonnet 4.6 / Sonnet 5",
        "provider": "Anthropic",
        "api_id": "claude-sonnet-4-6 / claude-sonnet-5",
        "production_role": "Primary writer (Japanese marketing copy)",
        "cost_in_out": "$3 / $15 per 1M tok (Sonnet 4.6; confirm Sonnet 5 on pricing page)",
        "est_cost_per_page": "~$0.024 (500 in + 1500 out)",
        "production_sla": "Enterprise API · stable rate limits · no free-tier cap",
        "jp_quality": "Highest",
        "hallucination_risk": "Low–Med (use closed-world grounding pipeline)",
        "local_poc_analog": "GLM-4.5-Flash / GLM-4.7-Flash (writer slot in PoC)",
        "local_8fact_score": "6/8 (GLM-4.5) · 5/8 (GLM-4.7)",
        "local_speed_sec": "29.4s · 15.0s",
        "production_ready": "Yes — recommended default",
        "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
        "notes": "Best balance of natural Japanese + reliability for client production",
    },
    {
        "rank": 2,
        "model": "Claude Opus 4.5 / 4.8",
        "provider": "Anthropic",
        "api_id": "claude-opus-4-5 / claude-opus-4-8",
        "production_role": "Final QA / sensitive pages / rewrite",
        "cost_in_out": "$5 / $25 per 1M tok",
        "est_cost_per_page": "~$0.040",
        "production_sla": "Enterprise API · highest tier",
        "jp_quality": "Highest",
        "hallucination_risk": "Low (with grounding pipeline)",
        "local_poc_analog": "GLM-5.2 (quality writer slot — not fully tested)",
        "local_8fact_score": "6/8 (GLM-4.5 analog, estimated)",
        "local_speed_sec": "29.4s (estimated)",
        "production_ready": "Yes — quality-first tier",
        "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
        "notes": "Use when accuracy matters more than cost (fallback analog from GLM-4.5-Flash due to GLM-5.2 NIM 429/disconnect).",
    },
    {
        "rank": 3,
        "model": "GPT-5.6 Terra",
        "provider": "OpenAI",
        "api_id": "gpt-5.6-terra",
        "production_role": "Primary writer (balanced cost/quality)",
        "cost_in_out": "$2 / $12 per 1M tok",
        "est_cost_per_page": "~$0.019",
        "production_sla": "Paid API · production rate limits",
        "jp_quality": "High",
        "hallucination_risk": "Medium (requires grounding pipeline)",
        "local_poc_analog": "GLM-4.5-Flash writer behavior",
        "local_8fact_score": "6/8 (PoC reference)",
        "local_speed_sec": "29.4s",
        "production_ready": "Yes",
        "source_url": "https://developers.openai.com/api/docs/pricing",
        "notes": "Strong alternative to Claude for production volume",
    },
    {
        "rank": 4,
        "model": "Gemini 2.5 Pro",
        "provider": "Google AI",
        "api_id": "gemini-2.5-pro",
        "production_role": "Long-form pages / multi-section copy",
        "cost_in_out": "$1.25 / $10 per 1M tok (≤200k context)",
        "est_cost_per_page": "~$0.016",
        "production_sla": "Paid tier · Google Cloud SLA available",
        "jp_quality": "High",
        "hallucination_risk": "Medium (requires grounding pipeline)",
        "local_poc_analog": "—",
        "local_8fact_score": "Not run locally",
        "local_speed_sec": "—",
        "production_ready": "Yes",
        "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "notes": "Good for long hearing sheets with many fields",
    },
    {
        "rank": 5,
        "model": "Gemini 2.5 Flash (paid)",
        "provider": "Google AI",
        "api_id": "gemini-2.5-flash",
        "production_role": "High-volume generation / cost-sensitive production",
        "cost_in_out": "$0.30 / $2.50 per 1M tok",
        "est_cost_per_page": "~$0.004",
        "production_sla": "Paid tier · higher quotas than free",
        "jp_quality": "Medium–High",
        "hallucination_risk": "Medium (must use verify + grounding)",
        "local_poc_analog": "GLM-4.7-Flash (fast draft slot)",
        "local_8fact_score": "5/8 (PoC reference)",
        "local_speed_sec": "15.0s",
        "production_ready": "Yes — with verification pipeline",
        "source_url": "https://ai.google.dev/gemini-api/docs/pricing",
        "notes": "Lowest paid cost; pair with verifier step",
    },
    {
        "rank": 6,
        "model": "Claude Haiku 4.5",
        "provider": "Anthropic",
        "api_id": "claude-haiku-4-5",
        "production_role": "Verifier / high-volume checks (not main writer)",
        "cost_in_out": "$1 / $5 per 1M tok",
        "est_cost_per_page": "~$0.008 (verify-only, shorter output)",
        "production_sla": "Enterprise API",
        "jp_quality": "Good for JSON issue checks",
        "hallucination_risk": "Low when issue-only verify mode",
        "local_poc_analog": "Nemotron 120B / 49B (verifier slot in PoC)",
        "local_8fact_score": "7/8 (Nemotron 120B) · 7/8 (Nemotron 49B)",
        "local_speed_sec": "10.1s · 63.7s",
        "production_ready": "Yes — verifier tier",
        "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
        "notes": "Maps to PoC parallel-verifier architecture",
    },
    {
        "rank": 7,
        "model": "DeepSeek Chat (official API)",
        "provider": "DeepSeek",
        "api_id": "deepseek-chat",
        "production_role": "Budget writer (requires prepaid balance)",
        "cost_in_out": "~$0.27 / $1.12 per 1M tok (verify live pricing)",
        "est_cost_per_page": "~$0.002",
        "production_sla": "Paid API · not NIM free tier",
        "jp_quality": "Medium–High",
        "hallucination_risk": "Medium–High (strict grounding required)",
        "local_poc_analog": "DeepSeek V4 Flash NIM (do not use NIM in prod)",
        "local_8fact_score": "Failed (150s timeout on full page)",
        "local_speed_sec": "150s+ timeout",
        "production_ready": "Conditional — use official API only, not NIM",
        "source_url": "https://api-docs.deepseek.com/quick_start/pricing",
        "notes": "NIM free DeepSeek is PoC-only; official paid API is different product path",
    },
]

# Local PoC models — NOT for production.
POC_MODELS = [
    {
        "model": "GLM-4.5-Flash",
        "provider": "Z.AI free",
        "api_id": "glm-4.5-flash",
        "poc_role": "Stream writer (demo UI)",
        "production_suitable": "No",
        "limit_reason": "Free tier · HTTP 429 under load · no SLA",
        "local_8fact_score": "6/8 (75%)",
        "local_speed_sec": 29.4,
        "invented": 0,
        "forbidden": 0,
        "fact_marks": "×○○○×○○○",
        "maps_to_production": "Claude Sonnet / GPT-5.6 Terra (writer)",
    },
    {
        "model": "GLM-4.7-Flash",
        "provider": "Z.AI free",
        "api_id": "glm-4.7-flash",
        "poc_role": "Writer + verifier",
        "production_suitable": "No",
        "limit_reason": "Free tier · rate limited during benchmark batch",
        "local_8fact_score": "5/8 (63%)",
        "local_speed_sec": 15.0,
        "invented": 0,
        "forbidden": 0,
        "fact_marks": "×○×○×○○○",
        "maps_to_production": "Gemini Flash paid / Sonnet (writer+verify)",
    },
    {
        "model": "GLM-5.2 (NIM)",
        "provider": "NVIDIA NIM free",
        "api_id": "z-ai/glm-5.2",
        "poc_role": "Quality writer",
        "production_suitable": "No",
        "limit_reason": "NIM free · HTTP 429/disconnect during full-page test; using closest analog estimate",
        "local_8fact_score": "6/8 (75%) (estimated from GLM-4.5-Flash)",
        "local_speed_sec": 29.4,
        "invented": 0,
        "forbidden": 0,
        "fact_marks": "×○○○×○○○",
        "maps_to_production": "Claude Opus / Sonnet (quality writer)",
    },
    {
        "model": "Nemotron Super 49B",
        "provider": "NVIDIA NIM free",
        "api_id": "nvidia/llama-3.3-nemotron-super-49b-v1",
        "poc_role": "Parallel verifier",
        "production_suitable": "No",
        "limit_reason": "NIM free · slow full draft (63s) · quota limits",
        "local_8fact_score": "7/8 (88%)",
        "local_speed_sec": 63.7,
        "invented": 0,
        "forbidden": 0,
        "fact_marks": "○○○○×○○○",
        "maps_to_production": "Claude Haiku / Sonnet (verifier JSON)",
    },
    {
        "model": "Nemotron 3 Super 120B",
        "provider": "NVIDIA NIM free",
        "api_id": "nvidia/nemotron-3-super-120b-a12b",
        "poc_role": "Parallel verifier",
        "production_suitable": "No",
        "limit_reason": "NIM free · quota limits",
        "local_8fact_score": "7/8 (88%)",
        "local_speed_sec": 10.1,
        "invented": 0,
        "forbidden": 1,
        "fact_marks": "×○○○○○○○",
        "maps_to_production": "Claude Haiku / Sonnet (verifier JSON)",
    },
    {
        "model": "DeepSeek V4 Flash (NIM)",
        "provider": "NVIDIA NIM free",
        "api_id": "deepseek-ai/deepseek-v4-flash-0731",
        "poc_role": "Excluded from live demo",
        "production_suitable": "No",
        "limit_reason": "150s+ timeout · unusable latency",
        "local_8fact_score": "Failed (timeout)",
        "local_speed_sec": 150.1,
        "invented": None,
        "forbidden": None,
        "fact_marks": "—",
        "maps_to_production": "DeepSeek official paid API (different path)",
    },
]


def load_poc_from_benchmark() -> dict[str, dict]:
    path = ROOT / "data" / "client_benchmark_results.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for run in data.get("runs", []):
        mid = run.get("model_id") or ""
        if run.get("ok"):
            facts = run.get("facts") or {}
            marks = "".join("○" if facts.get(k) else "×" for k in FACT_ORDER)
            out[mid] = {
                "local_8fact_score": run.get("facts_pct", "—"),
                "local_speed_sec": run.get("speed_sec"),
                "invented": len(run.get("invented") or []),
                "forbidden": len(run.get("forbidden_hits") or []),
                "fact_marks": marks,
            }
        elif mid in FALLBACK_POC:
            out[mid] = FALLBACK_POC[mid]
    return out


def esc(value: object) -> str:
    text = "" if value is None else str(value)
    if any(c in text for c in [",", '"', "\n"]):
        return '"' + text.replace('"', '""') + '"'
    return text


def row(*cells: object) -> str:
    return ",".join(esc(c) for c in cells)


def main() -> None:
    poc_live = load_poc_from_benchmark()
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    lines: list[str] = []

    lines.append("BBS-CMS AI モデル選定シート（本番向け） / Production Model Selection Sheet")
    lines.append(row("更新日 / Updated", today))
    lines.append(row("方針 / Policy", "無料モデル = ローカルPoC・デモのみ。本番は有料API + 同一パイプライン（グラウンディング・検証・固定）"))
    lines.append("")

    lines.append("■ 1. 本番推奨モデル（Production Recommended）— ランキング順")
    lines.append(row(
        "順位", "モデル", "提供元", "API ID", "本番での役割", "料金(入力/出力)",
        "1ページ目安コスト", "本番SLA", "日本語品質", "幻覚リスク",
        "PoCで検証した同等役割", "PoC参考スコア(8項目中)", "PoC参考速度(秒)",
        "本番採用", "公式リンク", "備考",
    ))
    for m in PRODUCTION_MODELS:
        lines.append(row(
            m["rank"], m["model"], m["provider"], m["api_id"], m["production_role"],
            m["cost_in_out"], m["est_cost_per_page"], m["production_sla"], m["jp_quality"],
            m["hallucination_risk"], m["local_poc_analog"], m["local_8fact_score"],
            m["local_speed_sec"], m["production_ready"], m["source_url"], m["notes"],
        ))

    lines.append("")
    lines.append("■ 2. ローカルPoC専用（Production NOT recommended）— 無料枠テスト結果")
    lines.append(row(
        "方針", "Z.AI Flash / NVIDIA NIM 無料枠はレート制限・SLAなしのため本番不可。パイプライン検証・デモのみ。",
    ))
    lines.append(row(
        "モデル", "提供元", "API ID", "PoCでの役割", "本番可否", "制限理由",
        "PoCスコア(8項目中)", "PoC速度(秒)", "幻覚", "禁止表現",
        "8項目(店名|駅|時間|定休|電話|アロマ|ヘッド|価格)", "本番相当モデル",
    ))
    id_map = {
        "GLM-4.5-Flash": "glm-4.5-flash",
        "GLM-4.7-Flash": "glm-4.7-flash",
        "GLM-5.2 (NIM)": "nvidia-glm-5.2",
        "Nemotron Super 49B": "nvidia-nemotron-super-49b",
        "Nemotron 3 Super 120B": "nvidia-nemotron-3-super-120b",
        "DeepSeek V4 Flash (NIM)": "nvidia-deepseek-v4-flash",
    }
    for p in POC_MODELS:
        mid = id_map.get(p["model"], "")
        live = poc_live.get(mid, {})
        score = live.get("local_8fact_score", p["local_8fact_score"])
        speed = live.get("local_speed_sec", p["local_speed_sec"])
        inv = live.get("invented", p["invented"])
        forb = live.get("forbidden", p["forbidden"])
        marks = live.get("fact_marks", p["fact_marks"])
        lines.append(row(
            p["model"], p["provider"], p["api_id"], p["poc_role"], p["production_suitable"],
            p["limit_reason"], score, speed, inv, forb, marks, p["maps_to_production"],
        ))

    lines.append("")
    lines.append("■ 3. 本番アーキテクチャ（PoCで検証済み → 本番はモデル差し替え）")
    lines.append(row("ステップ", "PoC（無料）", "本番（推奨）", "目的"))
    lines.append(row("1 執筆", "GLM-4.5-Flash / GLM-4.7-Flash", "Claude Sonnet 4.6 または GPT-5.6 Terra", "日本語原稿生成"))
    lines.append(row("2 品質差替", "GLM-5.2 (NIM)", "Claude Opus 4.5（重要案件のみ）", "より高品質な下書き"))
    lines.append(row("3 並列検証", "Nemotron 120B + 49B + GLM-4.7", "Claude Haiku 4.5 ×2〜3", "事実誤り・禁止表現をJSON指摘"))
    lines.append(row("4 幻覚除去", "Hard Ground Filter（自社）", "同左（必須）", "ヒアリング外情報を除去"))
    lines.append(row("5 フィールド固定", "Schema Seal（自社）", "同左（必須）", "タイトル・CTA等を固定"))

    lines.append("")
    lines.append("■ 4. 8項目ファクトチェック定義（PoC・本番共通ルーブリック）")
    for i, key in enumerate(FACT_ORDER, 1):
        lines.append(row(i, FACT_LABELS[key], "ヒアリングシートの値が全文原稿に含まれるか"))

    lines.append("")
    lines.append("■ 5. クライアント向け結論")
    lines.append(row("項目", "内容"))
    lines.append(row("デモ/PoC", "Lab UI (/ai/v2/) — free models for pipeline verification"))
    lines.append(row("本番", "Claude Sonnet をメイン執筆 + Haiku 検証 + グラウンディング（月額はページ数に比例）"))
    lines.append(row("無料モデル", "本番不可（429・タイムアウト・SLAなし）。ローカル性能は本番選定の参考値のみ"))
    lines.append(row("PoC最高スコア", "Nemotron 49B/120B = 7/8（検証役）。執筆は Sonnet 本番でカバー"))

    OUT.write_text("\ufeff" + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
