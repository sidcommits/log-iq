import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from models._validators import validate_aware_datetime


class TaskStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionableTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rca_id: str
    log_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    agent_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at", "updated_at")
    @classmethod
    def datetimes_must_be_aware(cls, v: datetime) -> datetime:
        return validate_aware_datetime(v)
