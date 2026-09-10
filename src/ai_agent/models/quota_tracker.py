"""Truthful free-tier quota chips for the lab UI.

Rules (no fake percentages):
- Ready            → last known state is usable (success, or never failed)
- Quota full · …  → real daily / long-window quota exhaustion
- Rate limit · …  → short retry 429 (RPM / burst); not "% used"
- Unavailable      → real 410 / retired model
- Timeout / error  → not treated as quota; chip stays Ready unless already exceeded
- % used           → only for confirmed daily windows with learned limit
- Short retry 429  → never sticky "100% used" after the model works again
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
QUOTA_PATH = ROOT / "data" / "quota_status.json"

_lock = threading.Lock()

# Google free-tier burst errors often say "Please retry in 20s" with limit: 20.
# Those are NOT daily RPD — treating them as daily caused sticky "100% used".
_SHORT_RETRY_SEC = 300.0

_RETRY_DELAY_RE = re.compile(
    r"retryDelay[\"']?\s*[:=]\s*[\"']?(\d+(?:\.\d+)?)\s*s",
    re.I,
)
_RETRY_IN_RE = re.compile(r"retry in\s+([0-9]+(?:\.[0-9]+)?)\s*s", re.I)
_QUOTA_VALUE_RE = re.compile(r"quotaValue[\"']?\s*[:=]\s*[\"']?(\d+)", re.I)
_LIMIT_RE = re.compile(r"\blimit:\s*(\d+)\b", re.I)
_QUOTA_ID_RE = re.compile(r"quotaId[\"']?\s*[:=]\s*[\"']([^\"']+)", re.I)
_METRIC_RE = re.compile(r"metric:\s*([a-z0-9_./]+)", re.I)


def _day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    try:
        from zoneinfo import ZoneInfo

        return now.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:
        return now.strftime("%Y-%m-%d")


def _pacific_midnight_utc_iso() -> str:
    now = datetime.now(UTC)
    try:
        from zoneinfo import ZoneInfo

        pacific = ZoneInfo("America/Los_Angeles")
        local = now.astimezone(pacific)
        nxt = (local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return nxt.astimezone(UTC).isoformat()
    except Exception:
        return (now + timedelta(hours=12)).replace(microsecond=0).isoformat()


def _load() -> dict[str, Any]:
    if not QUOTA_PATH.is_file():
        return {"models": {}, "updated_at": ""}
    try:
        raw = json.loads(QUOTA_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("models", {})
            return raw
    except Exception:
        pass
    return {"models": {}, "updated_at": ""}


def _save(data: dict[str, Any]) -> None:
    QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(UTC).isoformat()
    tmp = QUOTA_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(QUOTA_PATH)


def reset_all() -> None:
    """Wipe fabricated / stale chip state."""
    with _lock:
        _save({"models": {}, "updated_at": ""})


def _entry(data: dict[str, Any], model_id: str) -> dict[str, Any]:
    models = data.setdefault("models", {})
    row = models.get(model_id)
    if not isinstance(row, dict):
        row = {}
        models[model_id] = row
    row.setdefault("day", _day_key())
    row.setdefault("day_used", 0)
    row.setdefault("limit_rpd", None)  # only set when provider reveals quotaValue
    row.setdefault("limit_learned", False)
    row.setdefault("exceeded", False)
    row.setdefault("retired", False)
    row.setdefault("available_at", "")
    row.setdefault("quota_id", "")
    row.setdefault("last_error", "")
    row.setdefault("last_ok_at", "")
    row.setdefault("last_fail_at", "")
    return row


def _rotate_day(row: dict[str, Any]) -> None:
    day = _day_key()
    if row.get("day") != day:
        row["day"] = day
        row["day_used"] = 0
        # Daily free-tier reset: clear day-quota blocks only.
        qid = str(row.get("quota_id") or "").lower()
        if row.get("exceeded") and not row.get("retired") and "perday" in qid:
            row["exceeded"] = False
            row["available_at"] = ""
            row["last_error"] = ""


def record_success(model_id: str) -> None:
    mid = str(model_id or "").strip()
    if not mid:
        return
    with _lock:
        data = _load()
        row = _entry(data, mid)
        _rotate_day(row)
        row["day_used"] = int(row.get("day_used") or 0) + 1
        row["exceeded"] = False
        row["retired"] = False
        row["available_at"] = ""
        # Successful call after a short burst 429 → drop fake daily "% used".
        if str(row.get("window") or "") == "minute" or _is_short_burst_error(
            str(row.get("last_error") or "")
        ):
            row["limit_learned"] = False
            row["window"] = "minute"
        row["last_error"] = ""
        row["last_ok_at"] = datetime.now(UTC).isoformat()
        _save(data)


def _parse_retry_seconds(text: str) -> float | None:
    for pattern in (_RETRY_DELAY_RE, _RETRY_IN_RE):
        m = pattern.search(text or "")
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    m2 = re.search(r"retry[- ]after[\"']?\s*[:=]\s*[\"']?(\d+)", text or "", re.I)
    if m2:
        try:
            return float(m2.group(1))
        except ValueError:
            return None
    return None


def _is_short_burst_error(text: str) -> bool:
    """True for transient free-tier RPM / burst 429s (retry in seconds–few minutes)."""
    wait_s = _parse_retry_seconds(text)
    if wait_s is not None and wait_s <= _SHORT_RETRY_SEC:
        return True
    low = (text or "").lower()
    if "perminute" in low:
        return True
    # Google often omits quotaId and only says free_tier_requests + limit: N + retry in Xs.
    if "free_tier_requests" in low and wait_s is not None and wait_s <= _SHORT_RETRY_SEC:
        return True
    return False


def _message_quota_id(text: str) -> str:
    m = _QUOTA_ID_RE.search(text or "")
    return m.group(1) if m else ""


def _is_retired(text: str) -> bool:
    low = text.lower()
    return any(
        x in low
        for x in (
            "http 410",
            '"status":410',
            "status\":410",
            "has reached the end of its lifetime",
            "about:blank",
            '"title":"gone"',
        )
    )


def _is_quota(text: str) -> bool:
    low = text.lower()
    if _is_retired(text):
        return False
    # Timeouts / network are NOT quota.
    if any(x in low for x in ("timed out", "timeout", "read operation", "connect")):
        if "429" not in low and "resource_exhausted" not in low:
            return False
    return any(
        x in low
        for x in (
            "http 429",
            "resource_exhausted",
            "rate limit",
            "exceeded your current quota",
            "exceeded your current",
            "free_tier",
            "generaterequestsperday",
            "generaterequestsperminute",
            "resource has been exhausted",
            "code 1305",
            "too many requests",
        )
    ) or ("quota" in low and ("429" in low or "exhausted" in low or "exceed" in low))


def record_failure(model_id: str, error_text: str) -> None:
    mid = str(model_id or "").strip()
    if not mid:
        return
    text = str(error_text or "")
    retired = _is_retired(text)
    quota = _is_quota(text)
    if not retired and not quota:
        return

    with _lock:
        data = _load()
        row = _entry(data, mid)
        _rotate_day(row)
        row["last_error"] = text[:500]
        row["last_fail_at"] = datetime.now(UTC).isoformat()

        if retired:
            row["retired"] = True
            row["exceeded"] = True
            row["available_at"] = ""
            _save(data)
            return

        row["retired"] = False
        row["exceeded"] = True

        # Classify from THIS error text only — never trust a stale PerDay quota_id.
        msg_qid = _message_quota_id(text)
        metric_m = _METRIC_RE.search(text)
        metric = metric_m.group(1) if metric_m else ""
        wait_s = _parse_retry_seconds(text)
        low = text.lower()
        short_burst = _is_short_burst_error(text)

        limit_val = None
        qv = _QUOTA_VALUE_RE.search(text)
        if qv:
            try:
                limit_val = int(qv.group(1))
            except ValueError:
                limit_val = None
        if limit_val is None:
            lim_m = _LIMIT_RE.search(text)
            if lim_m:
                try:
                    limit_val = int(lim_m.group(1))
                except ValueError:
                    limit_val = None

        is_daily_msg = (
            "perday" in msg_qid.lower()
            or "generaterequestsperday" in low
            or "requests per day" in low
            or ("per day" in low and "per minute" not in low)
        ) and not short_burst

        is_rpm = short_burst or (
            "perminute" in msg_qid.lower()
            or "generaterequestsperminute" in low
            or "rate limit reached" in low
            or "too many requests" in low
            or (
                limit_val in {5, 10, 15, 20}
                and not is_daily_msg
                and "free_tier" in low
            )
        )

        if is_rpm and not is_daily_msg:
            row["quota_id"] = msg_qid or "GenerateRequestsPerMinute-FreeTier"
            row["window"] = "minute"
            # Burst / RPM must never drive sticky daily "% used" chips.
            row["limit_learned"] = False
            if limit_val and limit_val > 0:
                row["limit_rpd"] = limit_val  # tooltip only
        elif is_daily_msg:
            row["quota_id"] = msg_qid or row.get("quota_id") or "GenerateRequestsPerDay-FreeTier"
            row["window"] = "day"
            if limit_val and limit_val > 0:
                row["limit_rpd"] = limit_val
                row["limit_learned"] = True
                row["day_used"] = limit_val
        else:
            row["window"] = "minute"
            row["limit_learned"] = False
            if msg_qid:
                row["quota_id"] = msg_qid
            elif "free_tier_requests" in metric:
                row["quota_id"] = row.get("quota_id") or ""

        if wait_s is not None and wait_s > 0:
            row["available_at"] = (
                datetime.now(UTC) + timedelta(seconds=wait_s)
            ).isoformat()
        elif is_daily_msg:
            row["available_at"] = _pacific_midnight_utc_iso()
        else:
            row["available_at"] = (
                datetime.now(UTC) + timedelta(seconds=60)
            ).isoformat()

        _save(data)


def apply_probe_result(model_id: str, *, ok: bool, error: str = "") -> None:
    """Update chip from a live probe (preferred over stale guesses)."""
    if ok:
        record_success(model_id)
    elif error:
        record_failure(model_id, error)


def _fmt_available(iso: str) -> str:
    if not iso:
        return ""
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        secs = int((when - now).total_seconds())
        if secs <= 0:
            return "soon"
        if secs < 90:
            return f"~{secs}s"
        mins = (secs + 59) // 60
        if mins < 90:
            return f"~{mins}m"
        hours = (mins + 59) // 60
        if hours < 36:
            return f"~{hours}h"
        return when.astimezone(UTC).strftime("%m-%d %H:%MZ")
    except Exception:
        return ""


def status_for(model_id: str, *, pricing: str | None = None) -> dict[str, Any] | None:
    mid = str(model_id or "").strip()
    if not mid:
        return None
    with _lock:
        data = _load()
        row = _entry(data, mid)
        before = row.get("day")
        _rotate_day(row)
        if row.get("day") != before:
            _save(data)
        snap = dict(row)

    used = int(snap.get("day_used") or 0)
    learned = bool(snap.get("limit_learned"))
    try:
        limit_i = int(snap["limit_rpd"]) if snap.get("limit_rpd") is not None else None
    except (TypeError, ValueError):
        limit_i = None
    if not learned:
        limit_i = None

    exceeded = bool(snap.get("exceeded"))
    retired = bool(snap.get("retired"))
    available_at = str(snap.get("available_at") or "")

    # Cooldown finished → model is usable again (do not keep fake "unavailable").
    if exceeded and not retired:
        clear = False
        if available_at:
            try:
                when = datetime.fromisoformat(available_at.replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                if datetime.now(UTC) >= when:
                    clear = True
            except Exception:
                clear = True  # unparsable timestamp — don't block forever
        else:
            clear = True
        if clear:
            with _lock:
                data = _load()
                r2 = _entry(data, mid)
                if not r2.get("retired"):
                    r2["exceeded"] = False
                    r2["available_at"] = ""
                    if (
                        str(r2.get("window") or "") == "minute"
                        or "perminute" in str(r2.get("quota_id") or "").lower()
                        or _is_short_burst_error(str(r2.get("last_error") or ""))
                    ):
                        r2["limit_learned"] = False
                        r2["window"] = "minute"
                    _save(data)
            exceeded = False
            available_at = ""
            snap["exceeded"] = False
            snap["available_at"] = ""
            if (
                str(snap.get("window") or "") == "minute"
                or "perminute" in str(snap.get("quota_id") or "").lower()
                or _is_short_burst_error(str(snap.get("last_error") or ""))
            ):
                learned = False
                limit_i = None
                snap["window"] = "minute"

    # Heal sticky "100% used" left by misclassified short-burst 429s (model still works).
    last_err = str(snap.get("last_error") or "")
    if (
        not exceeded
        and not retired
        and learned
        and (
            str(snap.get("window") or "") == "minute"
            or _is_short_burst_error(last_err)
            or (
                limit_i in {5, 10, 15, 20}
                and used >= (limit_i or 0)
                and _parse_retry_seconds(last_err) is not None
                and (_parse_retry_seconds(last_err) or 0) <= _SHORT_RETRY_SEC
            )
        )
    ):
        with _lock:
            data = _load()
            r2 = _entry(data, mid)
            if not r2.get("retired") and not r2.get("exceeded"):
                r2["limit_learned"] = False
                r2["window"] = "minute"
                if "perday" in str(r2.get("quota_id") or "").lower() and _is_short_burst_error(
                    str(r2.get("last_error") or "")
                ):
                    r2["quota_id"] = "GenerateRequestsPerMinute-FreeTier"
                _save(data)
        learned = False
        limit_i = None
        snap["window"] = "minute"

    pct: int | None = None
    if learned and limit_i and limit_i > 0 and str(snap.get("window") or "day") != "minute":
        pct = int(min(100, round(100.0 * used / limit_i)))
        if exceeded:
            pct = 100

    window_out = str(snap.get("window") or "day")

    if retired or (exceeded and _is_retired(str(snap.get("last_error") or ""))):
        level = "exceeded"
        label = "Unavailable (retired)"
        pct = None
    elif exceeded:
        level = "exceeded"
        qid = str(snap.get("quota_id") or "").lower()
        avail = _fmt_available(available_at)
        retry_s = _parse_retry_seconds(last_err)
        is_rpm = (
            window_out == "minute"
            or "perminute" in qid
            or _is_short_burst_error(last_err)
            or (retry_s is not None and retry_s <= _SHORT_RETRY_SEC)
        )
        if is_rpm:
            label = "Rate limit"
            if avail:
                label = f"Rate limit · back {avail}"
            pct = None  # RPM cap is not daily usage %
            window_out = "minute"
        else:
            label = "Quota full"
            if avail:
                label = f"Quota full · back {avail}"
            if pct is None and learned:
                pct = 100
    elif learned and pct is not None and pct > 0:
        level = "warn" if pct >= 70 else "ok"
        label = f"{pct}% used"
    else:
        level = "ok"
        label = "Ready"
        pct = None

    return {
        "used": used if learned else None,
        "limit": limit_i,
        "pct": pct,
        "exceeded": exceeded and not retired,
        "retired": retired,
        "available_at": available_at if exceeded and not retired else "",
        "available_in": _fmt_available(available_at) if exceeded and not retired else "",
        "level": level,
        "label": label,
        "window": window_out,
        "limit_learned": learned,
    }


def lab_ids_for_remote(remote_or_id: str) -> list[str]:
    mid = str(remote_or_id or "").strip()
    if not mid:
        return []
    try:
        from ai_agent.models.registry import REGISTRY
    except Exception:
        return [mid]
    if mid in REGISTRY:
        return [mid]
    hits = [
        bid
        for bid, binding in REGISTRY.items()
        if binding.remote_id == mid or binding.api_model == mid
    ]
    return hits or [mid]


def note_http_error(remote_or_id: str, status_code: int, body: str) -> None:
    text = f"HTTP {int(status_code)}: {body or ''}"
    if int(status_code) not in {429, 410} and not _is_quota(text) and not _is_retired(text):
        return
    for mid in lab_ids_for_remote(remote_or_id):
        record_failure(mid, text)


def statuses_for_models(model_ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mid in model_ids:
        st = status_for(mid)
        if st:
            out[mid] = st
    return out
