"""Schemas for comparison, findings, metrics and AI endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import ApiModel, PageMeta

VerificationStatus = Literal["unverified", "verified", "not_improved", "inconclusive"]


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_run_id: str = Field(pattern=r"^run_[a-f0-9]{32}$")
    comparison_run_id: str = Field(pattern=r"^run_[a-f0-9]{32}$")
    include_diagnosis: bool = True


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_run_id: str | None = Field(default=None, pattern=r"^run_[a-f0-9]{32}$")


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: str
    description: str
    run_id: str | None = None
    event_id: str | None = None
    sequence: int | None = None
    step: str | None = None
    value: Any = None


class FindingOut(ApiModel):
    finding_id: str
    project_id: str
    run_id: str
    baseline_run_id: str | None = None
    category: str
    severity: Literal["high", "medium", "low"]
    confidence: Literal["high", "medium", "low"]
    title: str
    summary: str
    observation: str
    evidence: list[dict[str, Any]]
    hypothesis: str
    suggested_actions: list[str]
    regression_test: str | None = None
    step: str | None = None
    verification_status: VerificationStatus = "unverified"
    verification: dict[str, Any] | None = None
    source: str = "deterministic"
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime


class FindingList(ApiModel):
    items: list[FindingOut]
    meta: PageMeta


class AnalyzeResponse(ApiModel):
    run_id: str
    baseline_run_id: str | None
    baseline_selection: str
    findings: list[FindingOut]
    comparison_summary: dict[str, Any] | None = None


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=r"^run_[a-f0-9]{32}$", description="The corrected run to check.")


class AIChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    run_id: str | None = Field(default=None, pattern=r"^run_[a-f0-9]{32}$")
    finding_id: str | None = Field(default=None, pattern=r"^fnd_[a-f0-9]{32}$")


class AIChatResponse(BaseModel):
    source: Literal["ai_generated"] = "ai_generated"
    model: str
    answer: str
    context: dict[str, Any]
    disclaimer: str


class AIStatus(BaseModel):
    enabled: bool
    model: str | None
    reason: str | None = None


class MetricsOut(BaseModel):
    scope: dict[str, Any]
    totals: dict[str, Any]
    success_rate: float | None
    average_duration_ms: float | None
    duration_sample_size: int
    by_version: list[dict[str, Any]]
    activity: list[dict[str, Any]]
    findings: dict[str, Any]
    notes: list[str]
    generated_at: str
