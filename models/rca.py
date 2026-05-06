import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class RootCauseAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_id: str
    trace_id: str | None = None
    summary: str
    root_cause: str
    affected_services: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_fixes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
