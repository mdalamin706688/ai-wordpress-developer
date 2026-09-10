"""Structured pipeline logs without secrets or full hearing dumps."""

from __future__ import annotations

import logging
from typing import Any

from ai_agent.redact import redact

log = logging.getLogger("ai_agent.pipeline")

_SECRET_KEYS = {
    "api_key",
    "password",
    "authorization",
    "token",
    "secret",
    "wp_app_password",
}


def pipeline_log(
    *,
    job_id: str = "",
    stage: str,
    writer_model: str = "",
    verifier_model: str = "",
    attempt: int = 1,
    validation_status: str = "",
    issue_type: str = "",
    repair_count: int = 0,
    duration_ms: int = 0,
    wordpress_status: str = "",
    extra: str = "",
) -> None:
    msg = (
        f"job_id={job_id or '-'} stage={stage} writer_model={writer_model or '-'} "
        f"verifier_model={verifier_model or '-'} attempt={attempt} "
        f"validation_status={validation_status or '-'} issue_type={issue_type or '-'} "
        f"repair_count={repair_count} duration_ms={duration_ms} "
        f"wordpress_status={wordpress_status or '-'}"
    )
    if extra:
        msg += " extra=" + redact(extra)[:200]
    log.info(msg)


def scrub_payload(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (data or {}).items():
        low = str(key).lower()
        if any(token in low for token in _SECRET_KEYS):
            out[key] = "[REDACTED]"
        else:
            out[key] = value
    return out
