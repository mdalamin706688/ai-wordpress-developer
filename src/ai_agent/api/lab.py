"""AI Lab: config keys/prompts + multi-model write quality runs + Sheets status."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ai_agent.config import Settings, get_settings
from ai_agent.models.commercial import (
    accounts_from_config,
    apply_billing_override,
    billing_signal_in_error,
    commercial_for,
    mark_provider_paid,
    resolve_pricing,
    sync_provider_accounts,
)
from ai_agent.models.key_audit import (
    KEY_FIELD_PROVIDER,
    assert_model_key_matches,
    validate_key_for_field,
)
from ai_agent.models.registry import REGISTRY, ModelRegistry
from ai_agent.models.quota_tracker import status_for
from ai_agent.models.types import ChatMessage
from ai_agent.pipeline.ai_stack import StackResult, run_writer_production
from ai_agent.pipeline.copy_generator import (
    DEMO_SYSTEM_PROMPT,
    build_demo_user_prompt,
    demo_messages,
    parse_copy_json,
)
from ai_agent.pipeline.grounding import fact_pack
from ai_agent.pipeline.hearing_adapter import prepare_hearing_for_production
from ai_agent.pipeline.prompt_rules import default_lab_user_template, page_prompt_rules, prompt_sections_catalog
from ai_agent.pipeline.scoring import score_lab_copy
from ai_agent.pipeline.section_pages import merge_header_page_copies, merge_top_service_copies
from ai_agent.pipeline.site_composer import compose_site_draft
from ai_agent.pipeline.validate import WP_ALLOWED_STATUSES, prepare_copy_for_wordpress
from ai_agent.redact import redact
from ai_agent.wp.publisher import create_draft_pages
from fastapi.responses import StreamingResponse

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]
LAB_CONFIG_PATH = ROOT / "data" / "lab_config.json"

KEY_FIELDS = (
    "deepseek_api_key",
    "zai_api_key",
    "nvidia_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "gemini_paid_api_key",
    "moonshot_api_key",
    "minimax_api_key",
    "qwen_api_key",
)

PROVIDER_KEY_FIELD = {
    "deepseek": "deepseek_api_key",
    "zai": "zai_api_key",
    "nvidia": "nvidia_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "gemini": "gemini_api_key",
    "gemini_paid": "gemini_paid_api_key",
    "moonshot": "moonshot_api_key",
    "minimax": "minimax_api_key",
    "qwen": "qwen_api_key",
}

KEY_LABELS = {
    "deepseek_api_key": "DeepSeek",
    "zai_api_key": "Z.AI",
    "nvidia_api_key": "NVIDIA",
    "openai_api_key": "OpenAI",
    "anthropic_api_key": "Anthropic",
    "gemini_api_key": "Gemini (Free)",
    "gemini_paid_api_key": "Gemini (Paid)",
    "moonshot_api_key": "Moonshot (Kimi)",
    "minimax_api_key": "MiniMax",
    "qwen_api_key": "Qwen (DashScope)",
}

DEFAULT_SELECTED: list[str] = []

# Prefer these when a free-tier pick has no API key (Gemini Flash still needs a Google key).
FREE_KEY_FALLBACKS: list[str] = [
    "glm-4.5-flash",
    "glm-4.7-flash",
    "nvidia-nemotron-super-49b",
    "nvidia-minimax-m3",
    "nvidia-deepseek-v4-flash",
    "nvidia-kimi-k3",
    "nvidia-nemotron-3-super-120b",
]


def remap_models_missing_keys(
    selected: list[str],
    effective_keys: dict[str, str],
) -> tuple[list[str], list[dict[str, str]]]:
    """Swap free models whose provider key is empty to a ready free fallback.

    Paid models without a key are left as-is (Save still rejects them).
    Returns (new_selection, swaps) where each swap is {from, to}.
    """
    out: list[str] = []
    used: set[str] = set()
    swaps: list[dict[str, str]] = []

    def _has_key(model_id: str) -> bool:
        binding = REGISTRY.get(model_id)
        if not binding:
            return False
        field = PROVIDER_KEY_FIELD.get(binding.provider_name, "")
        return bool(str(effective_keys.get(field) or "").strip())

    def _next_fallback() -> str | None:
        for fb in FREE_KEY_FALLBACKS:
            if fb in used or fb not in REGISTRY:
                continue
            if _has_key(fb):
                return fb
        for mid, _binding in REGISTRY.items():
            if mid in used or not _has_key(mid):
                continue
            if "flash" in mid or mid.startswith("nvidia-") or mid.startswith("glm-4"):
                return mid
        return None

    for mid in selected:
        if mid not in REGISTRY:
            continue
        if _has_key(mid):
            if mid not in used:
                out.append(mid)
                used.add(mid)
            continue
        # No key for this provider — try free fallback instead of blocking Save.
        # Prefer a ready model already in the stack (avoid adding glm-4.7 when 4.5 is in).
        fb = next((x for x in out if _has_key(x)), None) or _next_fallback()
        if fb:
            if fb not in used:
                out.append(fb)
                used.add(fb)
            swaps.append({"from": mid, "to": fb})
            continue
        if mid not in used:
            out.append(mid)
            used.add(mid)
    return out, swaps


def _mask(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return text[:4] + "…" + text[-4:]


def _default_config() -> dict[str, Any]:
    return {
        "keys": {field: "" for field in KEY_FIELDS},
        "selected_models": list(DEFAULT_SELECTED),
        "system_prompt": DEMO_SYSTEM_PROMPT,
        "user_prompt_template": default_lab_user_template(),
        "updated_at": "",
        "provider_accounts": {},
    }


def _env_key_map() -> dict[str, str]:
    settings = get_settings()
    return {
        "deepseek_api_key": settings.deepseek_api_key,
        "zai_api_key": settings.zai_api_key,
        "nvidia_api_key": settings.nvidia_api_key,
        "openai_api_key": settings.openai_api_key,
        "anthropic_api_key": settings.anthropic_api_key,
        "gemini_api_key": settings.gemini_api_key,
        "gemini_paid_api_key": settings.gemini_paid_api_key,
        "moonshot_api_key": settings.moonshot_api_key,
        "minimax_api_key": settings.minimax_api_key,
        "qwen_api_key": settings.qwen_api_key,
    }


def _ready_model_ids(keys: dict[str, str] | None = None) -> list[str]:
    """Models whose provider key is available (lab override or .env)."""
    env = _env_key_map()
    keys = keys or {}
    ready: list[str] = []
    for model_id, binding in REGISTRY.items():
        field = PROVIDER_KEY_FIELD.get(binding.provider_name, "")
        if not field:
            continue
        if str(keys.get(field) or "").strip() or str(env.get(field) or "").strip():
            ready.append(model_id)
    return ready


def _default_selected(keys: dict[str, str] | None = None) -> list[str]:
    """No auto-pick — Config starts empty so users choose Free/Paid deliberately."""
    return []


def _pipeline_roles(model_ids: list[str]) -> tuple[str, str, list[str]]:
    """Standard lab roles from selection order (only selected models are used).

    1 model  → writer only (no Improve / no LLM Verifier; ground filter still runs)
    2 models → #1 writer · #2 verifier
    3+ models → #1 writer · #2 polish · #3+ verifiers
      (runtime uses up to 3 verifiers for latency SLA; further selections are ignored)
    """
    ids = [m for m in model_ids if m in REGISTRY]
    if not ids:
        return "", "", []
    writer = ids[0]
    if len(ids) == 1:
        return writer, "", []
    if len(ids) == 2:
        return writer, "", [ids[1]]
    # Cap verifiers at 3 (#3 #4 #5). #6+ stay in config but are not called.
    return writer, ids[1], ids[2:5]


def load_lab_config() -> dict[str, Any]:
    base = _default_config()
    if not LAB_CONFIG_PATH.is_file():
        base["selected_models"] = _default_selected(base["keys"])
        return base
    try:
        raw = json.loads(LAB_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        base["selected_models"] = _default_selected(base["keys"])
        return base
    keys = dict(base["keys"])
    keys.update(
        {
            k: str(v or "").strip()
            for k, v in (raw.get("keys") or {}).items()
            if k in KEY_FIELDS
        }
    )
    selected = raw.get("selected_models") or []
    # Drop removed / unknown ids (no silent remaps). Keep empty — do not auto-select.
    selected = [m for m in selected if m in REGISTRY]
    system_prompt = str(raw.get("system_prompt") or base["system_prompt"])
    user_prompt_template = str(
        raw.get("user_prompt_template") or base["user_prompt_template"]
    )
    planner_system_prompt = str(raw.get("planner_system_prompt") or "").strip()
    type24_extras_prompt = str(raw.get("type24_extras_prompt") or "").strip()
    type_prompts_raw = raw.get("type_prompts") if isinstance(raw.get("type_prompts"), dict) else {}
    # Satellite v2 templates use {page_rules} on purpose — keep them.
    satellite_user = (
        "{page_rules}" in user_prompt_template
        and (
            "sections" in user_prompt_template
            or "section id" in user_prompt_template.lower()
            or "Following the permitted facts" in user_prompt_template
        )
    )
    # Restore classic lab template if a prior {page_rules} experiment was saved.
    if not satellite_user and (
        "{page_rules}" in user_prompt_template or "--- TOP RULES ---" in user_prompt_template
    ):
        user_prompt_template = base["user_prompt_template"]
        system_prompt = base["system_prompt"]
    # Upgrade legacy short templates missing the 6-paragraph rule.
    elif (
        not satellite_user
        and "必ず6要素" not in user_prompt_template
        and "{hearing}" in user_prompt_template
    ):
        user_prompt_template = base["user_prompt_template"]
        system_prompt = base["system_prompt"]
    out = {
        "keys": keys,
        "selected_models": selected,
        "system_prompt": system_prompt,
        "user_prompt_template": user_prompt_template,
        "updated_at": str(raw.get("updated_at") or ""),
        "provider_accounts": dict(raw.get("provider_accounts") or {}),
    }
    if planner_system_prompt:
        out["planner_system_prompt"] = planner_system_prompt
    if type24_extras_prompt:
        out["type24_extras_prompt"] = type24_extras_prompt
    if type_prompts_raw:
        out["type_prompts"] = type_prompts_raw
    return out


def save_lab_config(cfg: dict[str, Any]) -> None:
    LAB_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAB_CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def settings_from_lab(cfg: dict[str, Any] | None = None) -> Settings:
    """Merge lab keys over .env settings for a run."""
    base = get_settings()
    cfg = cfg or load_lab_config()
    data = base.model_dump()
    for field in KEY_FIELDS:
        lab_val = str((cfg.get("keys") or {}).get(field) or "").strip()
        if lab_val:
            data[field] = lab_val
    return Settings(**data)


def _env_billing_flags() -> dict[str, bool | None]:
    settings = get_settings()
    return {"gemini": settings.gemini_billing_enabled}


def _effective_keys(cfg: dict[str, Any]) -> dict[str, str]:
    env = _env_key_map()
    lab = cfg.get("keys") or {}
    out: dict[str, str] = {}
    for field in KEY_FIELDS:
        out[field] = str(lab.get(field) or "").strip() or str(env.get(field) or "").strip()
    return out


def _pricing_for_model(
    model_id: str,
    provider: str,
    accounts: dict[str, Any],
) -> dict[str, Any]:
    return resolve_pricing(
        model_id,
        provider=provider,
        account=accounts.get(provider),
    )


def _pricing_tier(model_id: str, notes: str, provider: str) -> str:
    """Backward-compatible free|paid label (uses dynamic resolver with empty account)."""
    return str(
        resolve_pricing(model_id, provider=provider).get("pricing") or "paid"
    )


def public_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_lab_config()
    settings = get_settings()
    env_keys = _env_key_map()
    # Keep account status fresh when keys exist (TTL / fingerprint aware).
    sync_provider_accounts(
        cfg,
        keys=_effective_keys(cfg),
        env_flags=_env_billing_flags(),
        force=False,
    )
    accounts = accounts_from_config(cfg)
    keys_out: dict[str, Any] = {}
    for field in KEY_FIELDS:
        lab_val = str((cfg.get("keys") or {}).get(field) or "").strip()
        env_val = str(env_keys.get(field) or "").strip()
        effective = lab_val or env_val
        keys_out[field] = {
            "set": bool(effective),
            "masked": _mask(effective),
            "from_lab": bool(lab_val),
            "from_env": bool(env_val) and not bool(lab_val),
            "label": KEY_LABELS.get(field, field),
        }
    models = []
    effective = settings_from_lab(cfg)
    registry = ModelRegistry(effective)
    available = {item["id"]: item for item in registry.available()}
    for model_id, binding in REGISTRY.items():
        item = available.get(model_id) or {}
        key_field = PROVIDER_KEY_FIELD.get(binding.provider_name, "")
        pricing = _pricing_for_model(model_id, binding.provider_name, accounts)
        row = {
                "id": model_id,
                "name": binding.display_name,
                "provider": binding.provider_name,
                "notes": binding.notes,
                "pricing": pricing["pricing"],
                "pricing_reason": pricing.get("pricing_reason"),
                "free_tier_eligible": pricing.get("free_tier_eligible"),
                "list_input_usd_per_m": pricing.get("list_input_usd_per_m"),
                "list_output_usd_per_m": pricing.get("list_output_usd_per_m"),
                "account_tier": pricing.get("account_tier"),
                "billing_enabled": pricing.get("billing_enabled"),
                "key_field": key_field,
                "key_label": KEY_LABELS.get(key_field, key_field),
                "key_configured": bool(item.get("key_configured")),
                "selected": model_id in (cfg.get("selected_models") or []),
            }
        if pricing.get("pricing") == "free" or pricing.get("free_tier_eligible"):
            q = status_for(model_id, pricing=str(pricing.get("pricing") or ""))
            if q:
                row["quota"] = q
        models.append(row)
    return {
        "keys": keys_out,
        "selected_models": cfg.get("selected_models") or [],
        "system_prompt": cfg.get("system_prompt") or "",
        "user_prompt_template": cfg.get("user_prompt_template") or "",
        "planner_system_prompt": cfg.get("planner_system_prompt") or "",
        "type24_extras_prompt": cfg.get("type24_extras_prompt") or "",
        "type_prompts": cfg.get("type_prompts") or {},
        "prompt_sections": prompt_sections_catalog(),
        "models": models,
        "provider_accounts": {
            name: status.to_public() for name, status in accounts.items()
        },
        "updated_at": cfg.get("updated_at") or "",
        "google_client_id": settings.google_client_id,
        "google_sheets_folder_id": settings.google_sheets_folder_id,
        "pricing_note": "Prefer free models: Gemini Flash, NIM, and Z.AI Flash.",
    }



class LabConfigIn(BaseModel):
    keys: dict[str, str] = Field(default_factory=dict)
    selected_models: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    user_prompt_template: str = ""
    planner_system_prompt: str = ""
    type24_extras_prompt: str = ""
    type_prompts: dict[str, Any] = Field(default_factory=dict)
    clear_keys: list[str] = Field(default_factory=list)
    # e.g. {"gemini": true} means Google project has billing enabled → Flash becomes paid
    billing_overrides: dict[str, bool] = Field(default_factory=dict)


class LabBillingIn(BaseModel):
    provider: str = "gemini"
    billing_enabled: bool | None = None
    refresh: bool = True


class LabRunIn(BaseModel):
    hearing: dict[str, Any]
    model_ids: list[str] = Field(default_factory=list)
    # both|header|all (default) = all static header AI pages (model-site gnav).
    # Excludes blog/feature/column dynamic sub pages.
    # top | service | concept | … = single-page override (Advanced / R&D).
    page: str = "both"
    # production = write+verify+ground+seal+wordpress draft (default)
    # raw = single-model write only (R&D)
    mode: str = "production"
    use_lab_prompt: bool = False


class LabComposeIn(BaseModel):
    hearing: dict[str, Any]
    approved_copy: dict[str, Any] = Field(default_factory=dict)


def _invented(text: str) -> list[str]:
    found = []
    if "無料" in text:
        found.append("無料")
    if "提携駐車場" in text:
        found.append("提携駐車場")
    return found


def _build_messages(
    hearing: dict[str, Any],
    *,
    system_prompt: str,
    user_template: str,
    page: str,
) -> list[ChatMessage]:
    hearing_block = (
        "許可された事実:\n"
        + fact_pack(hearing)
        + "\nヒアリングJSON:\n"
        + json.dumps(hearing, ensure_ascii=False)
    )
    if "{page}" in user_template:
        user_template = user_template.replace("{page}", page or "top")
    if "{page_rules}" in user_template:
        user_template = user_template.replace("{page_rules}", page_prompt_rules(page or "top"))
    if "{hearing}" in user_template:
        user = user_template.replace("{hearing}", hearing_block)
    elif user_template.strip():
        user = user_template.strip() + "\n" + hearing_block
    else:
        user = build_demo_user_prompt(hearing, page=page)
    # Append predefined TOP/Service section rules (shown in Advanced tabs) for the active page.
    if "{page_rules}" not in (user_template or ""):
        user = user.rstrip() + "\n\n" + page_prompt_rules(page or "top")
    system = system_prompt.strip() or DEMO_SYSTEM_PROMPT
    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]


def _extra_body(model_id: str) -> dict[str, Any]:
    from ai_agent.pipeline.ai_stack import extra_body_for

    return dict(extra_body_for(model_id) or {})


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _run_pages(page: str | None, hearing: dict[str, Any] | None = None) -> list[str]:
    """Default production run writes all static header AI pages (model-site gnav).

    Excludes dynamic sub pages (blog posts, feature topics, column articles).
    Single page only when forced via LabRunIn.page.
    """
    from ai_agent.pipeline.prompt_rules import header_ai_page_ids

    key = (page or "both").strip().lower()
    if key in {"both", "all", "header", "top+service", "top_service"}:
        return header_ai_page_ids(hearing=hearing or {})
    if key in {"services"}:
        return ["service"]
    known = {
        "top",
        "concept",
        "service",
        "greeting",
        "menu",
        "faq",
        "feature",
        "access",
        "reviews",
    }
    if key in known:
        return [key]
    return ["top"]


def _messages_for_page(
    *,
    hearing: dict[str, Any],
    cfg: dict[str, Any],
    page: str,
    use_lab_prompt: bool,
) -> list[ChatMessage] | None:
    if not use_lab_prompt:
        return None
    return _build_messages(
        hearing,
        system_prompt=str(cfg.get("system_prompt") or ""),
        user_template=str(cfg.get("user_prompt_template") or ""),
        page=page,
    )


async def _produce_page_copy(
    *,
    registry: ModelRegistry,
    hearing: dict[str, Any],
    writer: str,
    quality: str,
    verifier_pool: list[str],
    mode: str,
    messages: list[ChatMessage] | None,
) -> StackResult:
    stack: StackResult | None = None
    async for kind, payload in run_writer_production(
        registry,
        hearing,
        writer=writer,
        quality_writer=quality if mode != "raw" else "",
        messages=messages,
        verifier_pool=verifier_pool,
    ):
        if kind == "done":
            stack = payload
    if stack is None:
        raise RuntimeError("production stack produced no result")
    return stack


def _section_text(value: Any) -> str:
    """Flatten a structured section value into console/CSV text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, dict):
                # Menu / service blocks / concept points
                if "name" in item and ("duration" in item or "price" in item):
                    lines.append(
                        " / ".join(
                            str(item.get(k) or "").strip()
                            for k in ("name", "duration", "price")
                            if str(item.get(k) or "").strip()
                        )
                    )
                elif "heading" in item and "body" in item:
                    head = str(item.get("heading") or "").strip()
                    body = str(item.get("body") or "").strip()
                    lines.append(f"{head}\n{body}".strip() if head else body)
                elif "title" in item and "body" in item:
                    lines.append(
                        f"{str(item.get('title') or '').strip()}：{str(item.get('body') or '').strip()}".strip("：")
                    )
                elif "q" in item or "a" in item:
                    q = str(item.get("q") or "").strip()
                    a = str(item.get("a") or "").strip()
                    lines.append(f"Q: {q}\nA: {a}".strip())
                else:
                    chunk = " ".join(str(v).strip() for v in item.values() if str(v).strip())
                    if chunk:
                        lines.append(chunk)
            else:
                s = str(item or "").strip()
                if s:
                    lines.append(s)
        return "\n".join(lines)
    if isinstance(value, dict):
        if value.get("enabled") is False:
            reason = str(value.get("reason_if_disabled") or "").strip()
            return f"（省略）{reason}".strip()
        # Prefer known field order for readable export.
        preferred = (
            "brand_name",
            "catchcopy",
            "subcopy",
            "heading",
            "lead",
            "body",
            "cta",
            "station",
            "address",
            "phone",
            "hours",
            "closed",
            "payment",
            "parking",
            "method",
            "items",
            "points",
            "services",
        )
        lines = []
        seen: set[str] = set()
        for key in preferred:
            if key not in value or key in {"enabled", "reason_if_disabled", "id"}:
                continue
            seen.add(key)
            chunk = _section_text(value.get(key))
            if chunk:
                lines.append(chunk)
        for key, raw in value.items():
            if key in seen or key in {"enabled", "reason_if_disabled", "id", "page", "checklist", "qa"}:
                continue
            chunk = _section_text(raw)
            if chunk:
                lines.append(chunk)
        return "\n".join(lines)
    return str(value).strip()


def _append_checklist_sections(
    out: list[dict[str, str]],
    *,
    page_key: str,
    wp_page: str,
    structured: dict[str, Any],
    checklist: list[dict[str, str]],
) -> None:
    for item in checklist:
        sid = str(item.get("id") or "").strip()
        if not sid:
            continue
        raw = structured.get(sid)
        text = _section_text(raw)
        if not text and sid in {"greeting", "reviews", "message", "items"}:
            text = "（省略）"
        out.append(
            {
                "id": f"{page_key}_{sid}",
                "wp_page": wp_page,
                "label_ja": str(item.get("web") or item.get("label") or sid),
                "label_en": str(item.get("label") or sid),
                "text": text,
            }
        )


def build_wp_sections(
    copy: dict[str, Any],
    wordpress: dict[str, Any] | None = None,
    *,
    hearing: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Labeled WordPress blocks for UI + CSV — all static header page checklists."""
    from ai_agent.pipeline.prompt_rules import HEADER_PAGES, section_items_for
    from ai_agent.pipeline.section_pages import build_section_bundle

    wp = wordpress or {}
    pages = {str(p.get("id") or ""): p for p in (wp.get("pages") or []) if isinstance(p, dict)}
    hearing = hearing or {}

    bundle = wp.get("sections") if isinstance(wp.get("sections"), dict) else None
    if not isinstance(bundle, dict) or not bundle.get("top"):
        bundle = build_section_bundle(hearing, copy, page="top")
        # Prefer per-page sections attached on WP pages when present.
        for p in pages.values():
            secs = p.get("sections")
            if isinstance(secs, dict) and secs.get("page"):
                bundle[str(secs.get("page"))] = secs
            elif isinstance(secs, dict) and p.get("id") == "home":
                bundle["top"] = secs
            elif isinstance(secs, dict) and p.get("id"):
                bundle[str(p["id"])] = secs

    sections: list[dict[str, str]] = []
    for meta in HEADER_PAGES:
        pid = str(meta["id"])
        wp_id = "home" if pid == "top" else str(meta.get("wp_id") or pid)
        page_obj = pages.get(wp_id) or pages.get(pid) or {}
        structured = bundle.get(pid) if isinstance(bundle.get(pid), dict) else {}
        if not structured and isinstance(page_obj.get("sections"), dict):
            structured = page_obj["sections"]

        sections.append(
            {
                "id": f"{pid}_title",
                "wp_page": wp_id,
                "label_ja": f"{meta.get('nav_label') or meta.get('label')} SEOタイトル",
                "label_en": f"{meta.get('label')} title",
                "text": str(page_obj.get("title") or structured.get("seo_title") or ""),
            }
        )
        sections.append(
            {
                "id": f"{pid}_slug",
                "wp_page": wp_id,
                "label_ja": f"{meta.get('nav_label') or meta.get('label')} スラッグ",
                "label_en": f"{meta.get('label')} slug",
                "text": str(page_obj.get("slug") or ("home" if pid == "top" else pid)),
            }
        )
        _append_checklist_sections(
            sections,
            page_key=pid,
            wp_page=wp_id,
            structured=structured,
            checklist=section_items_for(pid),
        )

    contact = pages.get("contact") or {}
    if contact:
        contact_body = contact.get("body_paragraphs") or []
        sections.append(
            {
                "id": "contact_page",
                "wp_page": "contact",
                "label_ja": "お問い合わせページ",
                "label_en": "Contact page",
                "text": "\n".join(str(x) for x in contact_body if str(x).strip())
                or str(hearing.get("phone") or ""),
            }
        )
    notes = str(copy.get("notes") or "").strip()
    if notes:
        sections.append(
            {
                "id": "notes",
                "wp_page": "home",
                "label_ja": "メモ",
                "label_en": "Notes",
                "text": notes,
            }
        )
    return sections


def _row_from_copy(
    *,
    run_at: str,
    model_id: str,
    copy: dict[str, Any],
    hearing: dict[str, Any],
    speed: float,
    latency_ms: int | None = None,
    estimated_usd: float | None = None,
    architecture: dict[str, Any] | None = None,
    models_used: list[str] | None = None,
) -> dict[str, Any]:
    score = score_lab_copy(copy, hearing)
    text = "\n".join(
        [
            str(copy.get("heading") or ""),
            str(copy.get("lead") or ""),
            str(copy.get("cta") or ""),
            *list(copy.get("body_paragraphs") or []),
        ]
    )
    invented = _invented(text)
    facts_hit = score.get("facts_hit") or 0
    facts_total = score.get("facts_total") or 0
    pct = score.get("facts_pct") or 0
    complete = bool(score.get("complete"))
    wp = compose_site_draft(hearing, copy)
    sections = build_wp_sections(copy, wp, hearing=hearing)
    return {
        "run_at": run_at,
        "model": model_id,
        "provider": REGISTRY[model_id].provider_name,
        "ok": True,
        "status": "OK" if complete else "PARTIAL",
        "complete": complete,
        "grade": "production",
        "speed_sec": speed,
        "latency_ms": latency_ms,
        "facts": f"{facts_hit}/{facts_total} ({pct}%)",
        "facts_hit": facts_hit,
        "facts_total": facts_total,
        "invented": invented,
        "forbidden": score.get("forbidden_hits") or [],
        "heading": copy.get("heading") or "",
        "lead": copy.get("lead") or "",
        "body": "\n".join(copy.get("body_paragraphs") or []),
        "cta": copy.get("cta") or "",
        "paragraphs": score.get("paragraphs") or 0,
        "chars": score.get("chars") or 0,
        "copy": copy,
        "score": score,
        "wordpress": wp,
        "sections": sections,
        "architecture": architecture or {},
        "models_used": models_used or [model_id],
        "estimated_usd": estimated_usd,
        "error": "",
        "raw_preview": "",
    }


def _fail_row(*, run_at: str, model_id: str, speed: float, error: str, raw: str = "") -> dict[str, Any]:
    return {
        "run_at": run_at,
        "model": model_id,
        "provider": REGISTRY[model_id].provider_name,
        "ok": False,
        "status": "FAIL",
        "complete": False,
        "speed_sec": speed,
        "facts": "—",
        "invented": [],
        "forbidden": [],
        "heading": "",
        "lead": "",
        "body": "",
        "cta": "",
        "paragraphs": 0,
        "chars": 0,
        "copy": {},
        "error": redact(error)[:800],
        "raw_preview": (raw or "")[:1200],
    }


def _model_pricing(model_id: str) -> str:
    binding = REGISTRY.get(model_id)
    if not binding:
        return "paid"
    cfg = load_lab_config()
    accounts = accounts_from_config(cfg)
    return str(
        resolve_pricing(
            model_id,
            provider=binding.provider_name,
            account=accounts.get(binding.provider_name),
        ).get("pricing")
        or "paid"
    )


def _learn_billing_from_error(exc: BaseException, *, model_id: str) -> None:
    """Learn paid account only for metered providers — never poison Gemini Flash."""
    binding = REGISTRY.get(model_id)
    if not binding:
        return
    if not billing_signal_in_error(str(exc)):
        return
    # Gemini Flash is free without billing; Pro 429 "billing" text must not flip Flash → paid.
    if binding.provider_name == "gemini":
        return
    terms = commercial_for(model_id)
    if terms and terms.free_tier_eligible:
        return
    cfg = load_lab_config()
    mark_provider_paid(
        cfg,
        binding.provider_name,
        detail=f"Learned from API error on {model_id}: {redact(str(exc))[:160]}",
        source="learned",
    )
    save_lab_config(cfg)


def _user_facing_llm_error(exc: BaseException, *, model_id: str) -> str:
    """Turn provider/HTTP failures into a clear message for Config / paid-key issues."""
    binding = REGISTRY.get(model_id)
    provider = binding.provider_name if binding else "provider"
    label = KEY_LABELS.get(PROVIDER_KEY_FIELD.get(provider, ""), provider)
    pricing = _model_pricing(model_id)
    raw = redact(str(exc) or "")
    low = raw.lower()
    free_tip = (
        " Try a free model instead: glm-4.5-flash, nvidia-minimax-m3, or gemini-3.5-flash-lite."
        if pricing == "paid"
        else ""
    )

    if "api key is missing" in low or "missing api key" in low:
        return (
            f"{label} API key is missing for model “{model_id}”. "
            f"Open Config, paste a valid {label} key, Save, then retry."
        )

    # Auth / key rejected / NIM model not enabled for this account
    if any(
        x in low
        for x in (
            "http 401",
            "http 403",
            "http 404",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "authentication",
            "permission_denied",
            "api_key_invalid",
            "invalid_api_key",
            "not found for account",
            "authentication failed",
        )
    ):
        if "not found for account" in low or (
            "http 404" in low and provider == "nvidia"
        ):
            return (
                f"NVIDIA NIM model “{model_id}” is not available for this API key "
                f"(not enabled on build.nvidia.com, or the NIM endpoint was removed). "
                f"Try nvidia-minimax-m3, nvidia-nemotron-super-49b, or glm-4.5-flash."
            )
        if pricing == "paid":
            return (
                f"Your {label} API key cannot use paid model “{model_id}”. "
                f"Check that the key is valid, billing/credits are enabled on the {label} account, "
                f"and this model is allowed for your plan.{free_tip}"
            )
        return (
            f"Your {label} API key was rejected for “{model_id}”. "
            f"Paste a valid key in Config (AI Studio / provider console), Save, then retry."
        )

    # Billing / no credits / payment required
    if any(
        x in low
        for x in (
            "http 402",
            "insufficient",
            "quota",
            "billing",
            "payment required",
            "credit",
            "balance",
            "spend limit",
            "no longer available to new users",
        )
    ):
        if pricing == "paid":
            return (
                f"Paid model “{model_id}” is blocked for this {label} key "
                f"(billing, credits, or plan access). Add credits / enable billing, "
                f"or switch models.{free_tip}"
            )
        return (
            f"Quota or access limit hit for “{model_id}” ({label}). "
            f"Wait for free-tier reset, or switch to another free model."
        )

    # Rate limits
    if "http 429" in low or "rate limit" in low or "resource_exhausted" in low:
        return (
            f"Rate limit reached for “{model_id}” ({label}). "
            f"Wait a minute and retry, or pick another model."
        )

    # Model id / availability
    if "http 404" in low or "not found" in low or "no longer available" in low:
        return (
            f"Model “{model_id}” is not available with this {label} key. "
            f"Pick another model in Config (Flash / Flash-Lite preferred for free tier)."
            f"{free_tip}"
        )

    # Empty / truncated JSON (common when Gemini thinking eats the token budget)
    if "empty content" in low or "did not return json" in low or "json copy" in low:
        return (
            f"Model “{model_id}” returned incomplete copy (often Gemini thinking truncates output). "
            f"Retry once, or use gemini-3.5-flash-lite / a free GLM Flash model."
        )

        return (
            f"Could not reach {label} for “{model_id}” (network/timeout). "
            f"Check connectivity and retry."
        )

    # Fallback: short, still actionable
    short = raw.replace("\n", " ").strip()
    if len(short) > 220:
        short = short[:217] + "…"
    if pricing == "paid":
        return (
            f"Paid model “{model_id}” failed via {label}: {short or 'unknown error'}."
            f"{free_tip}"
        )
    return f"Model “{model_id}” failed via {label}: {short or 'unknown error'}."


def _probe_base_urls(settings: Settings | None = None) -> dict[str, str]:
    s = settings or get_settings()
    return {
        "zai": s.zai_base_url,
        "gemini": s.gemini_base_url,
        "nvidia": s.nvidia_base_url,
        "deepseek": s.deepseek_base_url,
        "openai": s.openai_base_url,
        "anthropic": s.anthropic_base_url,
        "moonshot": s.moonshot_base_url,
        "minimax": s.minimax_base_url,
        "qwen": s.qwen_base_url,
    }


def _ensure_model_key(registry: ModelRegistry, model_id: str, cfg: dict[str, Any] | None = None) -> None:
    """Fail fast when key missing OR key does not belong to this model's provider."""
    from ai_agent.models.providers import LLMError

    provider, binding = registry.resolve(model_id)
    key = str(getattr(provider, "api_key", "") or "").strip()
    if not key:
        raise LLMError(f"{provider.name} API key is missing")
    settings = get_settings()
    try:
        assert_model_key_matches(
            model_id=model_id,
            provider=binding.provider_name,
            api_key=key,
            base_urls=_probe_base_urls(settings),
        )
    except ValueError as exc:
        raise LLMError(str(exc)) from exc


def _ensure_selected_keys(registry: ModelRegistry, model_ids: list[str]) -> None:
    """Validate keys for every selected model (writer + polish + verifiers)."""
    seen: set[str] = set()
    for mid in model_ids:
        binding = REGISTRY.get(mid)
        if not binding or binding.provider_name in seen:
            continue
        seen.add(binding.provider_name)
        _ensure_model_key(registry, mid)


@router.get("/v1/lab/config")
def lab_get_config() -> dict[str, Any]:
    cfg = load_lab_config()
    before = json.dumps(cfg.get("provider_accounts") or {}, sort_keys=True)
    # Ensure v2 per-type packs exist, but never clobber classic v1 flat prompts
    # (Japanese salon / brand_name・catchcopy TOP writer) with Type 3 satellite text.
    try:
        from ai_agent.v2.prompt_packs import merge_type_prompts

        before_tp = json.dumps(cfg.get("type_prompts") or {}, sort_keys=True, ensure_ascii=False)
        cfg["type_prompts"] = merge_type_prompts(cfg)
        after_tp = json.dumps(cfg.get("type_prompts") or {}, sort_keys=True, ensure_ascii=False)
        if after_tp != before_tp:
            cfg["updated_at"] = datetime.now(UTC).isoformat()
            save_lab_config(cfg)
    except Exception:
        pass
    out = public_config(cfg)
    after = json.dumps(cfg.get("provider_accounts") or {}, sort_keys=True)
    if after != before:
        save_lab_config(cfg)
    return out


@router.put("/v1/lab/config")
def lab_put_config(body: LabConfigIn) -> dict[str, Any]:
    cfg = load_lab_config()
    keys = dict(cfg["keys"])
    for field in body.clear_keys:
        if field in KEY_FIELDS:
            keys[field] = ""
    settings = get_settings()
    bases = _probe_base_urls(settings)
    pasted_errors: list[str] = []
    live_checked: set[str] = set()  # provider names already live-probed this request
    for field, value in (body.keys or {}).items():
        if field not in KEY_FIELDS:
            continue
        text = str(value or "").strip()
        if not text:
            continue
        # Ignore masked placeholders pasted back unchanged
        if "…" in text or text == "****":
            continue
        err = validate_key_for_field(field, text, base_urls=bases, live=True)
        if err:
            label = KEY_LABELS.get(field, field)
            pasted_errors.append(f"{label}: {err}")
            continue
        keys[field] = text
        provider = KEY_FIELD_PROVIDER.get(field)
        if provider:
            live_checked.add(provider)
    if pasted_errors:
        raise HTTPException(
            status_code=400,
            detail=(
                "API key rejected — use the correct provider key for each model. "
                + " | ".join(pasted_errors)
            ),
        )
    selected = [m for m in (body.selected_models or []) if m in REGISTRY]
    # Paid / selected models must have a working key for THEIR provider (lab or env).
    effective_preview = {
        field: str(keys.get(field) or "").strip()
        or str(_env_key_map().get(field) or "").strip()
        for field in KEY_FIELDS
    }
    # Free Gemini (etc.) still needs a Google key — without one, auto-use GLM/NIM
    # that already have keys in .env so Config is not stuck asking for a paste.
    selected, _key_swaps = remap_models_missing_keys(selected, effective_preview)
    checked_providers: set[str] = set()
    for mid in selected:
        binding = REGISTRY.get(mid)
        if not binding or binding.provider_name in checked_providers:
            continue
        checked_providers.add(binding.provider_name)
        field = PROVIDER_KEY_FIELD.get(binding.provider_name, "")
        key = effective_preview.get(field, "")
        # Newly pasted keys were live-probed above. For already-saved / .env keys,
        # only check shape + presence here so Save & continue stays fast.
        # Full live probe still runs when a key is pasted and again at draft run.
        try:
            assert_model_key_matches(
                model_id=mid,
                provider=binding.provider_name,
                api_key=key,
                base_urls=bases,
                live=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.system_prompt.strip():
        cfg["system_prompt"] = body.system_prompt
    if body.user_prompt_template.strip():
        cfg["user_prompt_template"] = body.user_prompt_template
    if body.planner_system_prompt.strip():
        cfg["planner_system_prompt"] = body.planner_system_prompt
    if body.type24_extras_prompt.strip():
        cfg["type24_extras_prompt"] = body.type24_extras_prompt
    if body.type_prompts:
        # Merge per-type system prompts (Type 1–4).
        existing = cfg.get("type_prompts") if isinstance(cfg.get("type_prompts"), dict) else {}
        merged_tp: dict[str, Any] = dict(existing)
        for tid, slot in body.type_prompts.items():
            if not isinstance(slot, dict):
                continue
            key = str(tid or "").strip().lower()
            if key not in {"type1", "type2", "type3", "type4"}:
                continue
            prev = merged_tp.get(key) if isinstance(merged_tp.get(key), dict) else {}
            next_slot = dict(prev)
            if str(slot.get("system_prompt") or "").strip():
                next_slot["system_prompt"] = str(slot.get("system_prompt") or "").strip()
            if str(slot.get("planner_system_prompt") or "").strip():
                next_slot["planner_system_prompt"] = str(slot.get("planner_system_prompt") or "").strip()
            if str(slot.get("user_prompt_template") or "").strip():
                next_slot["user_prompt_template"] = str(slot.get("user_prompt_template") or "").strip()
            merged_tp[key] = next_slot
        cfg["type_prompts"] = merged_tp
        # Do not sync type3 → flat system_prompt. v1 lab uses flat JP prompts;
        # v2 lab reads type_prompts.* per production type.
    # Keep type_prompts complete for v2, without overwriting classic v1 flat prompts.
    try:
        from ai_agent.v2.prompt_packs import merge_type_prompts

        cfg["type_prompts"] = merge_type_prompts(cfg)
    except Exception:
        pass
    cfg["keys"] = keys
    cfg["selected_models"] = selected
    for provider, enabled in (body.billing_overrides or {}).items():
        if provider in PROVIDER_KEY_FIELD:
            apply_billing_override(cfg, provider, billing_enabled=bool(enabled))
    cfg["updated_at"] = datetime.now(UTC).isoformat()
    sync_provider_accounts(
        cfg,
        keys=_effective_keys(cfg),
        env_flags=_env_billing_flags(),
        force=True,
    )
    save_lab_config(cfg)
    return public_config(cfg)


@router.post("/v1/lab/billing")
def lab_billing(body: LabBillingIn) -> dict[str, Any]:
    """Set or refresh provider billing tier (drives dynamic free/paid for Gemini Flash)."""
    cfg = load_lab_config()
    provider = (body.provider or "gemini").strip().lower()
    if provider not in PROVIDER_KEY_FIELD:
        raise HTTPException(status_code=400, detail=f"Unknown provider {provider}")
    if body.billing_enabled is not None:
        apply_billing_override(cfg, provider, billing_enabled=bool(body.billing_enabled))
    if body.refresh:
        sync_provider_accounts(
            cfg,
            keys=_effective_keys(cfg),
            env_flags=_env_billing_flags(),
            force=True,
        )
    cfg["updated_at"] = datetime.now(UTC).isoformat()
    save_lab_config(cfg)
    return public_config(cfg)


@router.get("/v1/lab/sheets/status")
def lab_sheets_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "oauthClientConfigured": bool(settings.google_client_id.strip()),
        "googleClientId": settings.google_client_id.strip(),
        "folderConfigured": bool(settings.google_sheets_folder_id.strip()),
        "folderId": settings.google_sheets_folder_id.strip(),
        "folderName": "BBS-CMS-LAB",
    }


@router.post("/v1/lab/run")
async def lab_run(body: LabRunIn) -> dict[str, Any]:
    hearing = prepare_hearing_for_production(body.hearing or {})
    if not str(hearing.get("business_name") or "").strip():
        raise HTTPException(status_code=400, detail="business_name is required")
    cfg = load_lab_config()
    model_ids = body.model_ids or cfg.get("selected_models") or DEFAULT_SELECTED
    model_ids = [m for m in model_ids if m in REGISTRY]
    if not model_ids:
        raise HTTPException(status_code=400, detail="no models selected")

    settings = settings_from_lab(cfg)
    registry = ModelRegistry(settings)
    pages = _run_pages(body.page, hearing)
    run_at = datetime.now(UTC).isoformat()
    mode = (body.mode or "production").strip().lower()
    writer, quality, verifier_pool = _pipeline_roles(model_ids)
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        _ensure_selected_keys(registry, model_ids)
        page_copies: dict[str, dict[str, Any]] = {}
        last_stack: StackResult | None = None
        for page in pages:
            page_hearing = dict(hearing)
            page_hearing["target_page"] = page
            messages = _messages_for_page(
                hearing=page_hearing,
                cfg=cfg,
                page=page,
                use_lab_prompt=body.use_lab_prompt,
            )
            stack = await _produce_page_copy(
                registry=registry,
                hearing=page_hearing,
                writer=writer,
                quality=quality,
                verifier_pool=verifier_pool,
                mode=mode,
                messages=messages,
            )
            page_copies[page] = stack.copy
            last_stack = stack
        if last_stack is None:
            raise RuntimeError("production stack produced no result")
        if len(page_copies) > 1:
            merged = merge_header_page_copies(hearing, page_copies)
        else:
            only = pages[0]
            merged = page_copies[only]
            hearing = dict(hearing)
            hearing["target_page"] = only
        speed = round((time.perf_counter() - started) * 1000) / 1000
        row = _row_from_copy(
            run_at=run_at,
            model_id=writer,
            copy=merged,
            hearing=hearing,
            speed=speed,
            estimated_usd=last_stack.estimated_usd,
            architecture=last_stack.architecture,
            models_used=last_stack.models_used,
        )
        row["roles"] = last_stack.roles or (last_stack.architecture or {}).get("roles") or {}
        row["stream_writer"] = last_stack.stream_writer
        row["quality_writer"] = last_stack.quality_writer
        row["verifiers"] = last_stack.verifiers
        row["validation"] = last_stack.validation or {}
        row["pages_written"] = pages
        if (last_stack.validation or {}).get("ok") is False:
            row["status"] = "NEEDS_REVIEW"
            row["validation_blocking"] = (last_stack.validation or {}).get("blocking") or []
        rows.append(row)
    except Exception as exc:  # noqa: BLE001 — lab boundary
        speed = round((time.perf_counter() - started) * 1000) / 1000
        _learn_billing_from_error(exc, model_id=writer)
        friendly = _user_facing_llm_error(exc, model_id=writer)
        rows.append(
            _fail_row(
                run_at=run_at,
                model_id=writer,
                speed=speed,
                error=friendly,
                raw=str(exc),
            )
        )

    return {
        "run_at": run_at,
        "mode": mode,
        "writer": writer,
        "quality_writer": quality,
        "verifiers": verifier_pool,
        "pages_written": _run_pages(body.page, hearing),
        "roles": {
            "writer": writer,
            "polish": quality or None,
            "verify": verifier_pool,
            "note": (
                "1 = write+verify (same); 2 = write+verify; "
                "3–5 = write+polish+up to 3 verifiers; 6+ extras unused."
            ),
        },
        "hearing": {
            "business_name": hearing.get("business_name"),
            "area": hearing.get("area"),
            "missing": hearing.get("missing") or [],
        },
        "models_ran": [writer],
        "pipeline_models": model_ids,
        "rows": rows,
        "sections": (rows[0].get("sections") if rows else []) or [],
    }


@router.post("/v1/lab/run/stream")
async def lab_run_stream(body: LabRunIn) -> StreamingResponse:
    hearing = prepare_hearing_for_production(body.hearing or {})
    if not str(hearing.get("business_name") or "").strip():
        raise HTTPException(status_code=400, detail="business_name is required")
    cfg = load_lab_config()
    model_ids = body.model_ids or cfg.get("selected_models") or DEFAULT_SELECTED
    model_ids = [m for m in model_ids if m in REGISTRY]
    if not model_ids:
        raise HTTPException(status_code=400, detail="no models selected")

    settings = settings_from_lab(cfg)
    registry = ModelRegistry(settings)
    pages = _run_pages(body.page, hearing)
    run_at = datetime.now(UTC).isoformat()
    mode = (body.mode or "production").strip().lower()
    writer, quality, verifier_pool = _pipeline_roles(model_ids)

    async def events():
        rows: list[dict[str, Any]] = []
        yield _sse(
            {
                "type": "start",
                "run_at": run_at,
                "mode": mode,
                "grade": "production",
                "writer": writer,
                "quality_writer": quality,
                "verifiers": verifier_pool,
                "pipeline_models": model_ids,
                "pages_written": pages,
                "roles": {
                    "writer": writer,
                    "polish": quality or None,
                    "verify": verifier_pool,
                },
                "hearing": {
                    "business_name": hearing.get("business_name"),
                    "area": hearing.get("area"),
                    "missing": hearing.get("missing") or [],
                },
            }
        )
        started = time.perf_counter()
        yield _sse(
            {
                "type": "model_start",
                "model": writer,
                "provider": REGISTRY[writer].provider_name,
                "pipeline": "header pages → verify → ground → seal → wordpress",
                "pages": pages,
            }
        )
        try:
            _ensure_selected_keys(registry, model_ids)
            page_copies: dict[str, dict[str, Any]] = {}
            last_stack: StackResult | None = None
            for page in pages:
                page_hearing = dict(hearing)
                page_hearing["target_page"] = page
                messages = _messages_for_page(
                    hearing=page_hearing,
                    cfg=cfg,
                    page=page,
                    use_lab_prompt=body.use_lab_prompt,
                )
                yield _sse(
                    {
                        "type": "stage",
                        "model": writer,
                        "id": f"write_{page}",
                        "label": f"Writing {page.upper()} page…",
                        "page": page,
                    }
                )
                stack: StackResult | None = None
                async for kind, payload in run_writer_production(
                    registry,
                    page_hearing,
                    writer=writer,
                    quality_writer=quality if mode != "raw" else "",
                    messages=messages,
                    verifier_pool=verifier_pool,
                ):
                    if kind == "token":
                        yield _sse(
                            {
                                "type": "token",
                                "model": writer,
                                "page": page,
                                "text": str(payload or ""),
                            }
                        )
                    elif kind == "progress":
                        yield _sse(
                            {
                                "type": "progress",
                                "model": writer,
                                "page": page,
                                **(payload if isinstance(payload, dict) else {}),
                            }
                        )
                    elif kind == "stage":
                        yield _sse(
                            {
                                "type": "stage",
                                "model": writer,
                                "page": page,
                                **(payload if isinstance(payload, dict) else {"id": str(payload)}),
                            }
                        )
                    elif kind == "done":
                        stack = payload
                if stack is None:
                    raise RuntimeError(f"production stack produced no result for page={page}")
                page_copies[page] = stack.copy
                last_stack = stack

            if last_stack is None:
                raise RuntimeError("production stack produced no result")
            work_hearing = dict(hearing)
            if len(page_copies) > 1:
                merged = merge_header_page_copies(work_hearing, page_copies)
            else:
                only = pages[0]
                merged = page_copies[only]
                work_hearing["target_page"] = only
            speed = round((time.perf_counter() - started) * 1000) / 1000
            row = _row_from_copy(
                run_at=run_at,
                model_id=writer,
                copy=merged,
                hearing=work_hearing,
                speed=speed,
                estimated_usd=last_stack.estimated_usd,
                architecture=last_stack.architecture,
                models_used=last_stack.models_used,
            )
            row["roles"] = last_stack.roles or (last_stack.architecture or {}).get("roles") or {}
            row["stream_writer"] = last_stack.stream_writer
            row["quality_writer"] = last_stack.quality_writer
            row["verifiers"] = last_stack.verifiers
            row["validation"] = last_stack.validation or {}
            row["pages_written"] = pages
            if (last_stack.validation or {}).get("ok") is False:
                row["status"] = "NEEDS_REVIEW"
                row["validation_blocking"] = (last_stack.validation or {}).get("blocking") or []
            rows.append(row)
            yield _sse({"type": "model_done", "model": writer, "row": row})
            yield _sse(
                {
                    "type": "done",
                    "run_at": run_at,
                    "mode": mode,
                    "rows": rows,
                    "sections": row.get("sections") or [],
                    "roles": row.get("roles") or {},
                    "models_used": last_stack.models_used,
                    "pages_written": pages,
                }
            )
        except Exception as exc:  # noqa: BLE001 — lab boundary
            speed = round((time.perf_counter() - started) * 1000) / 1000
            _learn_billing_from_error(exc, model_id=writer)
            friendly = _user_facing_llm_error(exc, model_id=writer)
            row = _fail_row(
                run_at=run_at,
                model_id=writer,
                speed=speed,
                error=friendly,
                raw=str(exc),
            )
            rows.append(row)
            yield _sse(
                {
                    "type": "error",
                    "model": writer,
                    "pricing": _model_pricing(writer),
                    "message": friendly,
                    "detail": redact(str(exc))[:400],
                }
            )
            yield _sse({"type": "model_done", "model": writer, "row": row})
            yield _sse(
                {
                    "type": "done",
                    "ok": False,
                    "run_at": run_at,
                    "mode": mode,
                    "rows": rows,
                    "sections": [],
                    "error": friendly,
                }
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v1/lab/wordpress/compose")
def lab_wordpress_compose(body: LabComposeIn) -> dict[str, Any]:
    hearing = prepare_hearing_for_production(body.hearing or {})
    copy = body.approved_copy or {}
    if not str(hearing.get("business_name") or "").strip():
        raise HTTPException(status_code=400, detail="business_name is required")
    if not str(copy.get("heading") or "").strip():
        raise HTTPException(status_code=400, detail="approved_copy.heading is required")
    copy, validation = prepare_copy_for_wordpress(copy, hearing)
    if validation.get("status") not in WP_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"error": "copy_not_safe_for_wordpress", "validation": validation},
        )
    site = compose_site_draft(hearing, copy)
    wp_plan = create_draft_pages(site, job_id="lab-compose", human_approved=False)
    return {
        "ok": True,
        "grade": "wordpress_draft",
        "publish": False,
        "human_approved": False,
        "note": "Deterministic WP draft package — never auto-published.",
        "site": site,
        "validation": validation,
        "wordpress_payloads": wp_plan.get("payloads") or [],
        "hearing": {
            "business_name": hearing.get("business_name"),
            "missing": hearing.get("missing") or [],
        },
    }
