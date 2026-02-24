from datetime import datetime, timezone
from typing import Optional

TIME_ZONE = timezone.utc


def to_utc_time_zone(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=TIME_ZONE)
    return value.astimezone(TIME_ZONE)


def get_now() -> datetime:
    """Get the current time"""
    return datetime.now(TIME_ZONE)
