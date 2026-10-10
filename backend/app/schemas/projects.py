from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import ApiModel, PageMeta


def _strip(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    environment: str | None = Field(default=None, max_length=64)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)

    _strip_name = field_validator("name", "description")(_strip)

    @field_validator("name")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("name must not be blank")
        return value


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    settings: ProjectSettings | None = None

    _strip_fields = field_validator("name", "description")(_strip)


class ProjectStats(BaseModel):
    total_runs: int = 0
    success_runs: int = 0
    failed_runs: int = 0
    last_run_at: datetime | None = None


class ProjectOut(ApiModel):
    project_id: str
    name: str
    description: str
    settings: dict[str, Any] = Field(default_factory=dict)
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime
    stats: ProjectStats | None = None


class KeyOut(ApiModel):
    key_id: str
    project_id: str
    prefix: str
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    active: bool


class KeyIssued(ApiModel):
    key_id: str
    project_id: str
    api_key: str = Field(description="Plaintext key. Shown exactly once; only its hash is stored.")
    prefix: str
    created_at: datetime


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._\-+]+$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class VersionOut(ApiModel):
    version_id: str
    project_id: str
    version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    run_count: int | None = None


class ProjectCreated(ApiModel):
    project: ProjectOut
    key: KeyIssued


class ProjectDetail(ApiModel):
    project: ProjectOut
    keys: list[KeyOut]
    versions: list[VersionOut]


class ProjectList(ApiModel):
    items: list[ProjectOut]
    meta: PageMeta


class KeyRotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revoke_existing: bool = True


class KeyRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_id: str | None = Field(default=None, description="Revoke one key. Omit to revoke all active keys.")


class KeyRevokeResult(ApiModel):
    revoked: list[str]


class KeyVerifyOut(ApiModel):
    project_id: str
    project_name: str
    key_id: str
