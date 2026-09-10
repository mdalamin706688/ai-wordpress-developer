from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


JobType = Literal["build_site", "build_page", "write_eval", "refine_section"]
JobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "partially_succeeded",
    "failed",
    "cancelled",
]


class CredentialIn(BaseModel):
    scheme: str = "wp_application_password"
    user: str = "bbs-ai-builder"
    password: str | None = None
    password_ciphertext: str | None = None
    kms_key_alias: str | None = None


class TargetIn(BaseModel):
    site_url: str | None = None
    rest_path_style: Literal["rest_route", "pretty"] = "rest_route"
    credential: CredentialIn | None = None


class InputIn(BaseModel):
    format: str = "normalized_json"
    data: dict[str, Any] = Field(default_factory=dict)


class OptionsIn(BaseModel):
    model_overrides: dict[str, str | None] = Field(default_factory=dict)
    budget: dict[str, int] = Field(
        default_factory=lambda: {"max_tokens": 2_000_000, "max_duration_sec": 1800}
    )
    research: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    models: list[str] = Field(default_factory=list)


class JobCreateRequest(BaseModel):
    job_type: JobType = "write_eval"
    site_id: int | None = None
    idempotency_key: str | None = None
    input: InputIn = Field(default_factory=InputIn)
    target: TargetIn | None = None
    site_capabilities: dict[str, Any] = Field(default_factory=dict)
    options: OptionsIn = Field(default_factory=OptionsIn)
    callback_url: str | None = None


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    accepted_at: datetime


class JobRecord(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    accepted_at: datetime
    updated_at: datetime
    site_id: int | None = None
    idempotency_key: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    progress: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
