from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from ai_agent.config import Settings, get_settings
from ai_agent.jobs.schemas import JobAccepted, JobCreateRequest, JobRecord, utcnow
from ai_agent.jobs.store import JobStore
from ai_agent.pipeline.orchestrator import run_job

router = APIRouter()
_store = JobStore()


def require_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.intake_api_key:
        return
    if x_api_key != settings.intake_api_key:
        raise HTTPException(status_code=401, detail="invalid API key")


@router.post("/v1/jobs", response_model=JobAccepted, status_code=202)
def create_job(
    body: JobCreateRequest,
    _: None = Depends(require_api_key),
) -> JobAccepted:
    if body.idempotency_key:
        existing = _store.find_by_idempotency(body.idempotency_key)
        if existing:
            return JobAccepted(
                job_id=existing.job_id,
                status=existing.status,
                accepted_at=existing.accepted_at,
            )

    now = utcnow()
    request = body.model_dump(mode="json")
    cred = ((request.get("target") or {}).get("credential") or {})
    if cred.get("password"):
        cred["password"] = "[REDACTED]"
    rec = JobRecord(
        job_id=JobStore.new_id(),
        job_type=body.job_type,
        status="queued",
        accepted_at=now,
        updated_at=now,
        site_id=body.site_id,
        idempotency_key=body.idempotency_key,
        request=request,
    )
    _store.create(rec)
    threading.Thread(target=run_job, args=(_store, rec.job_id), daemon=True).start()
    return JobAccepted(job_id=rec.job_id, status=rec.status, accepted_at=rec.accepted_at)


@router.get("/v1/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: str, _: None = Depends(require_api_key)) -> JobRecord:
    rec = _store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    return rec


@router.post("/v1/jobs/{job_id}/cancel", response_model=JobRecord)
def cancel_job(job_id: str, _: None = Depends(require_api_key)) -> JobRecord:
    rec = _store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="job not found")
    if rec.status in ("succeeded", "failed", "cancelled", "partially_succeeded"):
        return rec
    updated = _store.update(job_id, status="cancelled", progress="cancelled")
    assert updated is not None
    return updated
