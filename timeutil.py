"""
Single place for all date/time handling.

Rule used across the project:
  * The database always stores UTC (naive datetimes, no tzinfo).
  * The API always sends UTC with an explicit 'Z' (e.g. 2026-10-05T06:51:00Z),
    so the browser knows exactly which instant it is.
  * Anything shown to people (frontend, CSV export) is converted to the
    display timezone below (India Standard Time, UTC+05:30).
"""
from datetime import datetime, timedelta, timezone

# India has no daylight saving, so a fixed offset is exact and avoids needing
# the 'tzdata' package on Windows.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def utcnow() -> datetime:
    """Current time in UTC as a naive datetime (what we store in MySQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value: datetime) -> datetime:
    """Treat naive datetimes from the DB as UTC; convert aware ones to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_ist(value: datetime) -> datetime:
    """Convert a stored (UTC) datetime to India time for display."""
    return as_utc(value).astimezone(IST)
