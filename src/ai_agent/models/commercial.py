"""Dynamic free/paid resolution (catalog × account billing tier).

Industry pattern:
- Model catalog: list price + whether a standing free tier exists
- Per-provider account status: free | paid | unknown (probed / learned / override)
- Effective UI pricing = f(catalog, account) — not a hard-coded label per model id

Gemini Flash / Flash-Lite: always free. Only Pro Preview is paid.
A Pro quota error must not flip Flash to paid.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

PricingLabel = Literal["free", "paid"]
AccountTier = Literal["free", "paid", "unknown"]

# How long a successful probe is trusted before re-check on next key save.
PROBE_TTL_SEC = 6 * 60 * 60


@dataclass(frozen=True)
class ModelCommercial:
    """Static commercial terms for a model id (provider list price)."""

    free_tier_eligible: bool
    input_usd_per_m: float
    output_usd_per_m: float
    notes: str = ""


# Catalog: eligibility + list prices (USD / 1M tokens). Source of truth for "can be free".
MODEL_COMMERCIAL: dict[str, ModelCommercial] = {
    # Z.AI — Flash $0; official paid flagships
    "glm-4.7-flash": ModelCommercial(True, 0.0, 0.0, "Z.AI Flash $0"),
    "glm-4.5-flash": ModelCommercial(True, 0.0, 0.0, "Z.AI Flash $0"),
    "glm-5.3": ModelCommercial(False, 1.40, 4.40, "Z.AI metered"),
    "glm-5.2": ModelCommercial(False, 1.40, 4.40, "Z.AI metered"),
    "glm-5.1": ModelCommercial(False, 1.40, 4.40, "Z.AI metered"),
    "glm-5": ModelCommercial(False, 1.00, 3.20, "Z.AI metered"),
    "glm-5-turbo": ModelCommercial(False, 1.20, 4.00, "Z.AI metered"),
    # NVIDIA NIM — free serverless for Developer Program
    "nvidia-deepseek-v4-flash": ModelCommercial(True, 0.0, 0.0, "NIM free"),
    "nvidia-nemotron-3-super-120b": ModelCommercial(True, 0.0, 0.0, "NIM free"),
    "nvidia-nemotron-super-49b": ModelCommercial(True, 0.0, 0.0, "NIM free"),
    "nvidia-kimi-k3": ModelCommercial(True, 0.0, 0.0, "NIM free"),
    "nvidia-minimax-m3": ModelCommercial(True, 0.0, 0.0, "NIM free"),
    # Official NVIDIA Nemotron (customer nvapi key) — parallel to Moonshot/MiniMax official
    "nemotron-3-super-120b": ModelCommercial(False, 0.0, 0.0, "NVIDIA official — paid"),
    "nemotron-super-49b": ModelCommercial(False, 0.0, 0.0, "NVIDIA official — paid"),
    # Gemini — 3.5 Flash + Lite free; 3.6+ / Pro paid (GEMINI_PAID_API_KEY)
    "gemini-3.5-flash-lite": ModelCommercial(True, 0.0, 0.0, "free"),
    "gemini-3.5-flash": ModelCommercial(True, 0.0, 0.0, "free"),
    "gemini-3.5-flash-lite-paid": ModelCommercial(False, 0.0, 0.0, "paid — Flash-Lite, client billed key"),
    "gemini-3.5-flash-paid": ModelCommercial(False, 0.0, 0.0, "paid — Flash 3.5, client billed key"),
    "gemini-3.6-flash": ModelCommercial(False, 0.0, 0.0, "paid — client Gemini billed key"),
    "gemini-3.7-flash": ModelCommercial(False, 0.0, 0.0, "paid — client Gemini billed key"),
    "gemini-3.8-flash": ModelCommercial(False, 0.0, 0.0, "paid — latest Flash, client billed key"),
    "gemini-3.1-pro-preview": ModelCommercial(False, 1.25, 10.0, "paid"),
    # Always-metered providers
    "deepseek-v4-flash": ModelCommercial(False, 0.44, 1.32, "DeepSeek prepaid"),
    "deepseek-v4-pro": ModelCommercial(False, 1.32, 3.96, "DeepSeek prepaid"),
    "gpt-5.6-terra": ModelCommercial(False, 0.0, 0.0, "OpenAI metered"),
    "gpt-5.6-sol": ModelCommercial(False, 0.0, 0.0, "OpenAI metered"),
    "gpt-5.6-luna": ModelCommercial(False, 0.0, 0.0, "OpenAI metered"),
    "kimi-k3": ModelCommercial(False, 0.0, 0.0, "Moonshot official — paid"),
    "minimax-m3": ModelCommercial(False, 0.0, 0.0, "MiniMax official — paid"),
    "qwen-flash": ModelCommercial(False, 0.05, 0.40, "DashScope — trial then paid"),
    "qwen-plus": ModelCommercial(False, 0.40, 1.20, "DashScope — trial then paid"),
    "claude-sonnet-5": ModelCommercial(False, 0.0, 0.0, "Anthropic metered"),
    "claude-haiku-4.5": ModelCommercial(False, 0.0, 0.0, "Anthropic metered"),
    "claude-opus-4.5": ModelCommercial(False, 0.0, 0.0, "Anthropic metered"),
    "claude-opus-5": ModelCommercial(False, 5.0, 25.0, "Anthropic Opus 5 — paid"),
}

# Providers whose accounts are always treated as paid when a key is present.
ALWAYS_PAID_PROVIDERS = frozenset(
    {"openai", "anthropic", "deepseek", "moonshot", "minimax", "qwen", "gemini_paid"}
)
# Providers whose catalog free-tier models stay free (list price $0 or NIM / AI Studio Flash).
ALWAYS_FREE_PROVIDERS = frozenset({"nvidia", "zai", "gemini"})


@dataclass
class ProviderAccountStatus:
    provider: str
    usage_tier: AccountTier = "unknown"
    billing_enabled: bool | None = None
    source: str = "default"  # default | probe | learned | override | env
    checked_at: str = ""
    key_fingerprint: str = ""
    detail: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "usage_tier": self.usage_tier,
            "billing_enabled": self.billing_enabled,
            "source": self.source,
            "checked_at": self.checked_at,
            "detail": self.detail,
        }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def key_fingerprint(api_key: str) -> str:
    text = (api_key or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def commercial_for(model_id: str) -> ModelCommercial | None:
    return MODEL_COMMERCIAL.get(model_id)


def resolve_pricing(
    model_id: str,
    *,
    provider: str,
    account: ProviderAccountStatus | None = None,
) -> dict[str, Any]:
    """Return effective pricing label + audit fields for UI / gating."""
    terms = commercial_for(model_id)
    account = account or ProviderAccountStatus(provider=provider)

    if provider in ALWAYS_PAID_PROVIDERS:
        return {
            "pricing": "paid",
            "pricing_reason": "provider_always_metered",
            "free_tier_eligible": False,
            "list_input_usd_per_m": float(terms.input_usd_per_m) if terms else 0.0,
            "list_output_usd_per_m": float(terms.output_usd_per_m) if terms else 0.0,
            "account_tier": account.usage_tier,
            "billing_enabled": True,
        }

    if terms and not terms.free_tier_eligible:
        return {
            "pricing": "paid",
            "pricing_reason": "no_free_tier",
            "free_tier_eligible": False,
            "list_input_usd_per_m": terms.input_usd_per_m,
            "list_output_usd_per_m": terms.output_usd_per_m,
            "account_tier": account.usage_tier,
            "billing_enabled": account.billing_enabled,
        }

    # Free-tier eligible models are always free in UI (Flash / NIM / Z.AI).
    # Account "billing learned" must never flip these to paid.
    eligible = True if terms is None else terms.free_tier_eligible
    if eligible:
        return {
            "pricing": "free",
            "pricing_reason": (
                "provider_zero_list_price"
                if provider in ALWAYS_FREE_PROVIDERS
                else "free_tier_eligible_no_billing_required"
            ),
            "free_tier_eligible": True,
            "list_input_usd_per_m": float(terms.input_usd_per_m) if terms else 0.0,
            "list_output_usd_per_m": float(terms.output_usd_per_m) if terms else 0.0,
            "account_tier": "free",
            "billing_enabled": False,
        }

    return {
        "pricing": "paid",
        "pricing_reason": "default_paid",
        "free_tier_eligible": False,
        "list_input_usd_per_m": 0.0,
        "list_output_usd_per_m": 0.0,
        "account_tier": account.usage_tier,
        "billing_enabled": account.billing_enabled,
    }


def account_from_dict(provider: str, raw: dict[str, Any] | None) -> ProviderAccountStatus:
    raw = raw or {}
    tier = str(raw.get("usage_tier") or "unknown")
    if tier not in {"free", "paid", "unknown"}:
        tier = "unknown"
    billing = raw.get("billing_enabled")
    if billing is not None:
        billing = bool(billing)
    return ProviderAccountStatus(
        provider=provider,
        usage_tier=tier,  # type: ignore[arg-type]
        billing_enabled=billing,
        source=str(raw.get("source") or "default"),
        checked_at=str(raw.get("checked_at") or ""),
        key_fingerprint=str(raw.get("key_fingerprint") or ""),
        detail=str(raw.get("detail") or ""),
    )


def accounts_from_config(cfg: dict[str, Any] | None) -> dict[str, ProviderAccountStatus]:
    raw = (cfg or {}).get("provider_accounts") or {}
    out: dict[str, ProviderAccountStatus] = {}
    if not isinstance(raw, dict):
        return out
    for provider, value in raw.items():
        if isinstance(value, dict):
            out[str(provider)] = account_from_dict(str(provider), value)
    return out


def save_account(cfg: dict[str, Any], status: ProviderAccountStatus) -> None:
    accounts = dict(cfg.get("provider_accounts") or {})
    accounts[status.provider] = {
        "usage_tier": status.usage_tier,
        "billing_enabled": status.billing_enabled,
        "source": status.source,
        "checked_at": status.checked_at,
        "key_fingerprint": status.key_fingerprint,
        "detail": status.detail,
    }
    cfg["provider_accounts"] = accounts


def mark_provider_paid(
    cfg: dict[str, Any],
    provider: str,
    *,
    detail: str,
    source: str = "learned",
) -> ProviderAccountStatus:
    status = ProviderAccountStatus(
        provider=provider,
        usage_tier="paid",
        billing_enabled=True,
        source=source,
        checked_at=_now_iso(),
        key_fingerprint=str(
            ((cfg.get("provider_accounts") or {}).get(provider) or {}).get(
                "key_fingerprint"
            )
            or ""
        ),
        detail=detail[:240],
    )
    save_account(cfg, status)
    return status


def apply_billing_override(
    cfg: dict[str, Any],
    provider: str,
    *,
    billing_enabled: bool,
) -> ProviderAccountStatus:
    prev = account_from_dict(provider, (cfg.get("provider_accounts") or {}).get(provider))
    status = ProviderAccountStatus(
        provider=provider,
        usage_tier="paid" if billing_enabled else "free",
        billing_enabled=billing_enabled,
        source="override",
        checked_at=_now_iso(),
        key_fingerprint=prev.key_fingerprint,
        detail=(
            "Operator marked Google billing enabled"
            if billing_enabled
            else "Operator marked Google free tier (no billing)"
        ),
    )
    save_account(cfg, status)
    return status


def _probe_stale(status: ProviderAccountStatus, fingerprint: str) -> bool:
    if not status.checked_at or status.key_fingerprint != fingerprint:
        return True
    if status.source == "override":
        return False
    try:
        checked = datetime.fromisoformat(status.checked_at.replace("Z", "+00:00"))
        return (datetime.now(UTC) - checked).total_seconds() > PROBE_TTL_SEC
    except ValueError:
        return True


def probe_gemini_account(
    api_key: str,
    *,
    previous: ProviderAccountStatus | None = None,
    env_billing: bool | None = None,
) -> ProviderAccountStatus:
    """Probe Gemini key health + resolve free vs billed.

    API keys alone do not expose Cloud Billing. Production strategy:
    1. Env override GEMINI_BILLING_ENABLED
    2. Operator override (previous.source == override)
    3. Validate key against Generative Language API
    4. Default to free tier until a billing error is learned
    """
    fp = key_fingerprint(api_key)
    if not api_key.strip():
        return ProviderAccountStatus(
            provider="gemini",
            usage_tier="unknown",
            billing_enabled=None,
            source="default",
            checked_at=_now_iso(),
            detail="No Gemini API key",
        )

    if previous and previous.source == "override" and previous.key_fingerprint == fp:
        return previous

    if env_billing is True:
        return ProviderAccountStatus(
            provider="gemini",
            usage_tier="paid",
            billing_enabled=True,
            source="env",
            checked_at=_now_iso(),
            key_fingerprint=fp,
            detail="GEMINI_BILLING_ENABLED=true",
        )
    if env_billing is False:
        return ProviderAccountStatus(
            provider="gemini",
            usage_tier="free",
            billing_enabled=False,
            source="env",
            checked_at=_now_iso(),
            key_fingerprint=fp,
            detail="GEMINI_BILLING_ENABLED=false",
        )

    if previous and not _probe_stale(previous, fp) and previous.source in {
        "probe",
        "learned",
        "env",
    }:
        return previous

    # Flash stays free without Cloud Billing. Do not inherit "learned paid" from Pro 429s.
    detail = "Key valid; Flash models are free"
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.get(
                "https://generativelanguage.googleapis.com/v1beta/openai/models",
                headers={"Authorization": f"Bearer {api_key.strip()}"},
            )
            if res.status_code in {401, 403}:
                return ProviderAccountStatus(
                    provider="gemini",
                    usage_tier="unknown",
                    billing_enabled=None,
                    source="probe",
                    checked_at=_now_iso(),
                    key_fingerprint=fp,
                    detail=f"Key rejected HTTP {res.status_code}",
                )
            if res.status_code >= 400:
                detail = f"Probe HTTP {res.status_code}; Flash treated as free"
            else:
                detail = "Key OK. Gemini Flash models are free; Pro Preview is paid."
    except httpx.HTTPError as exc:
        detail = f"Probe network error ({exc.__class__.__name__}); defaulting free tier"

    return ProviderAccountStatus(
        provider="gemini",
        usage_tier="free",
        billing_enabled=False,
        source="probe",
        checked_at=_now_iso(),
        key_fingerprint=fp,
        detail=detail,
    )


def probe_provider_account(
    provider: str,
    api_key: str,
    *,
    previous: ProviderAccountStatus | None = None,
    env_flags: dict[str, bool | None] | None = None,
) -> ProviderAccountStatus:
    env_flags = env_flags or {}
    if provider == "gemini":
        return probe_gemini_account(
            api_key,
            previous=previous,
            env_billing=env_flags.get("gemini"),
        )
    if provider == "gemini_paid":
        # Billed client key — always paid when present.
        if not (api_key or "").strip():
            return ProviderAccountStatus(
                provider=provider,
                usage_tier="unknown",
                billing_enabled=None,
                source="default",
                checked_at=_now_iso(),
                detail="No GEMINI_PAID_API_KEY configured",
            )
        return ProviderAccountStatus(
            provider=provider,
            usage_tier="paid",
            billing_enabled=True,
            source="default",
            checked_at=_now_iso(),
            key_fingerprint=key_fingerprint(api_key),
            detail="Client Gemini billed key (Paid chip models)",
        )
    if provider in ALWAYS_PAID_PROVIDERS:
        return ProviderAccountStatus(
            provider=provider,
            usage_tier="paid",
            billing_enabled=True,
            source="default",
            checked_at=_now_iso(),
            key_fingerprint=key_fingerprint(api_key),
            detail="Provider is metered (no standing free Flash tier)",
        )
    if provider in ALWAYS_FREE_PROVIDERS:
        return ProviderAccountStatus(
            provider=provider,
            usage_tier="free",
            billing_enabled=False,
            source="default",
            checked_at=_now_iso(),
            key_fingerprint=key_fingerprint(api_key),
            detail="Provider Flash/NIM list price is $0",
        )
    return ProviderAccountStatus(
        provider=provider,
        usage_tier="unknown",
        billing_enabled=None,
        source="default",
        checked_at=_now_iso(),
        key_fingerprint=key_fingerprint(api_key),
    )


def billing_signal_in_error(text: str) -> bool:
    low = (text or "").lower()
    return any(
        token in low
        for token in (
            "http 402",
            "billing",
            "payment required",
            "insufficient",
            "credit",
            "spend limit",
            "billing_not_active",
            "require billing",
        )
    )


PROVIDER_KEY_FIELDS = {
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


def sync_provider_accounts(
    cfg: dict[str, Any],
    *,
    keys: dict[str, str],
    env_flags: dict[str, bool | None] | None = None,
    force: bool = False,
) -> dict[str, ProviderAccountStatus]:
    """Refresh account status for providers that have keys."""
    field_to_provider = {v: k for k, v in PROVIDER_KEY_FIELDS.items()}
    existing = accounts_from_config(cfg)
    updated: dict[str, ProviderAccountStatus] = dict(existing)

    for field, key in keys.items():
        provider = field_to_provider.get(field)
        if not provider or not str(key or "").strip():
            continue
        prev = existing.get(provider)
        fp = key_fingerprint(key)
        if (
            not force
            and prev
            and not _probe_stale(prev, fp)
            and prev.source in {"probe", "learned", "env", "override"}
        ):
            updated[provider] = prev
            continue
        status = probe_provider_account(
            provider,
            key,
            previous=prev,
            env_flags=env_flags,
        )
        updated[provider] = status
        save_account(cfg, status)

    return updated
