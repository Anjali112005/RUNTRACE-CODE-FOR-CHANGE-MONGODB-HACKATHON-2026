from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer

from ..utils.timeutil import iso


class ApiModel(BaseModel):
    """Base response model: serialises datetimes as ISO-8601 UTC with a trailing Z."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _serialize_datetimes(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return iso(value)
        return value


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Message(BaseModel):
    message: str
