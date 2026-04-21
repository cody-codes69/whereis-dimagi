"""Small, dependency-light helpers used across routers & services."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from dateutil import parser as dateparser


def to_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize a datetime to naive UTC for SQLite storage/comparison."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 (or loose) timestamp and return naive UTC.

    Returns ``None`` if ``value`` is falsy. Raises ``ValueError`` on
    un-parseable input (callers decide how to surface it).
    """
    if not value:
        return None
    dt = dateparser.parse(value)
    return to_naive_utc(dt)


_SLUG_RX = re.compile(r"[^a-z0-9]+")


def derive_display_name(identifier: str) -> str:
    """Best-effort display name from an email or phone identifier."""
    if "@" in identifier:
        local = identifier.split("@", 1)[0]
        return local.replace(".", " ").replace("_", " ").title()
    return identifier
