import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AnomalyResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_id: str
    score: float = Field(ge=0.0, le=1.0)
    is_anomaly: bool
    threshold: float
    reviewed: bool = False
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
