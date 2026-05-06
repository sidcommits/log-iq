from datetime import datetime


def validate_aware_datetime(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return v
