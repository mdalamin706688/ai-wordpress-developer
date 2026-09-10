"""Closed-world generation job: writer → schema → ground → verifier → final validate → draft."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ai_agent.pipeline.claims import apply_semantic_verdicts, freeze_missing, missing_preserved
from ai_agent.pipeline.copy_generator import parse_copy_json
from ai_agent.pipeline.grounding import ground_copy
from ai_agent.pipeline.japanese import repair_copy_grammar
from ai_agent.pipeline.observability import pipeline_log
from ai_agent.pipeline.schema import SchemaError, seal_structured_fields
from ai_agent.pipeline.site_composer import compose_site_draft
from ai_agent.pipeline.validate import (
    STATUS_BLOCKED,
    STATUS_FAILED,
    WP_ALLOWED_STATUSES,
    prepare_copy_for_wordpress,
)
from ai_agent.pipeline.verify import apply_issues_audited, parse_verifier_report
from ai_agent.wp.publisher import create_draft_pages

WriterFn = Callable[[dict[str, Any]], str]
VerifierFn = Callable[[dict[str, Any], dict[str, Any]], str]


def run_generation_job(
    hearing: dict[str, Any],
    *,
    writer: WriterFn,
    verifier: VerifierFn | None = None,
    job_id: str = "job",
    writer_model: str = "",
    verifier_model: str = "",
    schema_retries: int = 1,
    wp_transport: Any | None = None,
    write_wordpress: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    pipeline_log(
        job_id=job_id,
        stage="write",
        writer_model=writer_model,
        verifier_model=verifier_model,
        attempt=1,
    )
    copy: dict[str, Any] | None = None
    last_error = ""
    attempts = schema_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            raw = writer(hearing)
            copy = parse_copy_json(raw, hearing=hearing)
            pipeline_log(
                job_id=job_id,
                stage="writer_schema",
                writer_model=writer_model,
                attempt=attempt,
                validation_status="PASS",
            )
            break
        except SchemaError as exc:
            last_error = str(exc)
            pipeline_log(
                job_id=job_id,
                stage="writer_schema",
                writer_model=writer_model,
                attempt=attempt,
                validation_status=STATUS_FAILED,
                issue_type="SCHEMA",
            )
            copy = None
            if attempt >= attempts:
                return _fail(
                    job_id,
                    "SCHEMA_ERROR",
                    last_error or "invalid AI output",
                    started,
                    writer_model=writer_model,
                    verifier_model=verifier_model,
                )
        except Exception as exc:
            return _fail(
                job_id,
                "FAILED",
                str(exc),
                started,
                writer_model=writer_model,
                verifier_model=verifier_model,
            )

    if copy is None:
        return _fail(
            job_id,
            "SCHEMA_ERROR",
            last_error or "invalid AI output",
            started,
            writer_model=writer_model,
            verifier_model=verifier_model,
        )

    copy, source_report = prepare_copy_for_wordpress(copy, hearing)
    grounded = ground_copy(copy, hearing)
    sealed = seal_structured_fields(grounded, hearing)
    repairs = list(source_report.get("repairs") or [])
    verifier_report: dict[str, Any] = {"status": "SKIPPED", "issues": []}
    if verifier is not None:
        try:
            verifier_report = parse_verifier_report(verifier(hearing, sealed))
            sealed, _applied, v_repairs = apply_issues_audited(
                sealed, verifier_report.get("issues") or [], hearing
            )
            repairs.extend(v_repairs)
            claims = verifier_report.get("claims") or []
            if claims:
                for key in ("title", "heading", "lead", "cta", "notes"):
                    sealed[key] = apply_semantic_verdicts(str(sealed.get(key) or ""), claims)
                paras = sealed.get("body_paragraphs") or []
                if isinstance(paras, list):
                    sealed["body_paragraphs"] = [
                        apply_semantic_verdicts(str(p), claims) for p in paras
                    ]
            sealed = repair_copy_grammar(sealed, hearing)
        except Exception as exc:
            return _fail(
                job_id,
                "FAILED",
                f"verifier failed: {exc}",
                started,
                writer_model=writer_model,
                verifier_model=verifier_model,
            )

    final, validation = prepare_copy_for_wordpress(sealed, hearing, repairs=repairs)
    status = str(validation.get("status") or STATUS_FAILED)
    audit = dict(validation.get("audit") or {})
    frozen_missing = freeze_missing(hearing)
    audit["missing_items_preserved"] = True
    site = None
    wp_result = None
    if status in WP_ALLOWED_STATUSES and validation.get("ok"):
        site = compose_site_draft(hearing, final)
        site_missing = list((site.get("qa") or {}).get("missing") or site.get("missing") or [])
        preserved = missing_preserved(hearing, site_missing)
        audit["missing_items_preserved"] = preserved
        if site.get("qa"):
            site["qa"]["repairs"] = [
                {
                    "field": str(item.get("field") or ""),
                    "type": str(item.get("type") or ""),
                    "reason": str(item.get("reason") or ""),
                }
                for item in repairs
            ]
            site["qa"]["verification_status"] = status
            site["qa"]["missing_items_preserved"] = preserved
            site["qa"]["audit"] = audit
        if not preserved:
            status = STATUS_FAILED
            validation["ok"] = False
            validation["status"] = STATUS_FAILED
            audit["status"] = STATUS_FAILED
            site = None
        elif write_wordpress:
            wp_result = create_draft_pages(
                site,
                job_id=job_id,
                human_approved=False,
                transport=wp_transport,
            )
            if not wp_result.get("ok"):
                return {
                    "ok": False,
                    "status": STATUS_FAILED,
                    "error": wp_result.get("error") or "wordpress_write_failed",
                    "copy": final,
                    "site": None,
                    "validation": validation,
                    "verifier": verifier_report,
                    "repairs": repairs,
                    "wordpress": wp_result,
                    "job_id": job_id,
                    "human_approved": False,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
    elif status == STATUS_BLOCKED:
        site = None

    duration_ms = int((time.perf_counter() - started) * 1000)
    pipeline_log(
        job_id=job_id,
        stage="done",
        writer_model=writer_model,
        verifier_model=verifier_model,
        validation_status=status,
        repair_count=len(repairs),
        duration_ms=duration_ms,
        wordpress_status="draft" if site else "",
    )
    return {
        "ok": status in WP_ALLOWED_STATUSES and bool(validation.get("ok")),
        "status": status,
        "copy": final,
        "site": site,
        "validation": validation,
        "audit": audit,
        "qa": (site or {}).get("qa")
        or {
            "missing": freeze_missing(hearing),
            "warnings": [],
            "repairs": repairs,
            "verification_status": status,
            "missing_items_preserved": audit.get("missing_items_preserved"),
            "audit": audit,
        },
        "verifier": verifier_report,
        "repairs": repairs,
        "wordpress": wp_result,
        "job_id": job_id,
        "human_approved": False,
        "writer_model": writer_model,
        "verifier_model": verifier_model,
        "duration_ms": duration_ms,
    }


def _fail(
    job_id: str,
    status: str,
    error: str,
    started: float,
    *,
    writer_model: str = "",
    verifier_model: str = "",
) -> dict[str, Any]:
    pipeline_log(
        job_id=job_id,
        stage="failed",
        writer_model=writer_model,
        verifier_model=verifier_model,
        validation_status=STATUS_FAILED,
        issue_type=status,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return {
        "ok": False,
        "status": STATUS_FAILED,
        "error": error,
        "error_code": status,
        "copy": None,
        "site": None,
        "wordpress": None,
        "human_approved": False,
        "job_id": job_id,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
