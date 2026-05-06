import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SeverityLevel(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRACE = "TRACE"
    UNKNOWN = "UNKNOWN"


class LogEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime
    severity: SeverityLevel
    service: str
    environment: str
    trace_id: str | None = None
    span_id: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    source: str

    @field_validator("timestamp")
    @classmethod
    def must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return v
