import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models._validators import validate_aware_datetime


class RootCauseAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_id: str
    trace_id: str | None = None
    summary: str
    root_cause: str
    affected_services: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_fixes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_aware(cls, v: datetime) -> datetime:
        return validate_aware_datetime(v)
