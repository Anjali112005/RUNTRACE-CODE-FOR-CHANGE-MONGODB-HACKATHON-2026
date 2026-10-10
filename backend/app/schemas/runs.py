from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..utils.timeutil import ensure_utc
from .common import ApiModel, PageMeta

RunStatus = Literal["running", "success", "failed", "timed_out"]
FinishStatus = Literal["success", "failed"]
EventStatus = Literal["success", "failed", "info", "skipped"]


class RunStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9._\-+]+$")
    environment: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    client_run_key: str | None = Field(
        default=None, min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_\-]+$",
        description="Client-generated idempotency key. Retrying a start with the same key returns the same run.",
    )


class EventError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(default="Error", max_length=200)
    message: str = Field(default="", max_length=20000)
    traceback: str | None = Field(default=None, max_length=50000)


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str | None = Field(
        default=None, pattern=r"^evt_[a-f0-9]{32}$",
        description="Optional client-generated ID (evt_<32 hex>) that makes retries idempotent.",
    )
    sequence: int = Field(ge=0, le=1_000_000)
    event_type: str = Field(default="step", pattern=r"^[a-z][a-z0-9_]{0,31}$")
    name: str = Field(min_length=1, max_length=200)
    status: EventStatus = "success"
    timestamp: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0, le=7 * 86_400_000)
    input_summary: Any = None
    output_summary: Any = None
    error: EventError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class EventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[EventIn] = Field(min_length=1)


class RunFinish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: FinishStatus
    error_summary: str | None = Field(default=None, max_length=4000)
    summary: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = Field(default=None, ge=0, le=7 * 86_400_000)


class RunOut(ApiModel):
    run_id: str
    project_id: str
    project_name: str | None = None
    version_id: str | None = None
    version: str | None = None
    name: str
    status: RunStatus
    environment: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: float | None = None
    error_summary: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    event_count: int = 0
    failed_event_count: int = 0
    is_demo: bool = False
    source: str = "sdk"


class RunList(ApiModel):
    items: list[RunOut]
    meta: PageMeta


class EventOut(ApiModel):
    event_id: str
    run_id: str
    project_id: str
    sequence: int
    event_type: str
    name: str
    status: str
    timestamp: datetime
    duration_ms: float | None = None
    input_summary: Any = None
    output_summary: Any = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventResult(BaseModel):
    event_id: str
    sequence: int
    result: Literal["created", "duplicate"]


class EventIngestResponse(BaseModel):
    run_id: str
    accepted: int
    duplicates: int
    results: list[EventResult]


class EventList(ApiModel):
    run_id: str
    items: list[EventOut]
    total: int
