from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware current datetime in UTC."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize aware values to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime must include timezone information")
    return value.astimezone(UTC)

