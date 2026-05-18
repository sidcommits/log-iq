import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models._validators import validate_aware_datetime
from models.log_event import LogEvent


class AnomalyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_id: str
    score: float = Field(ge=0.0, le=1.0)
    is_anomaly: bool
    threshold: float = Field(ge=0.0, le=1.0)
    reviewed: bool = False
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    log: LogEvent | None = None

    @field_validator("detected_at")
    @classmethod
    def detected_at_must_be_aware(cls, v: datetime) -> datetime:
        return validate_aware_datetime(v)
