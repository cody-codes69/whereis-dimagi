"""Physics-based sanity check: flag implausible travel between updates."""

from __future__ import annotations

from datetime import datetime

from ..config import settings
from ..utils import to_naive_utc
from .strategies import haversine_km


def validate_physics(
    prev_lat: float | None,
    prev_lng: float | None,
    prev_time: datetime | None,
    new_lat: float | None,
    new_lng: float | None,
    new_time: datetime,
    max_kmh: float | None = None,
) -> list[str]:
    """Return a list of warning tags (possibly empty)."""
    max_kmh = max_kmh if max_kmh is not None else settings.max_speed_kmh
    warnings: list[str] = []
    if None in (prev_lat, prev_lng, prev_time, new_lat, new_lng):
        return warnings

    prev_time = to_naive_utc(prev_time)
    new_time = to_naive_utc(new_time)
    assert prev_time is not None and new_time is not None

    km = haversine_km(prev_lat, prev_lng, new_lat, new_lng)  # type: ignore[arg-type]
    secs = (new_time - prev_time).total_seconds()
    if secs <= 0:
        if km > 1:
            warnings.append("non_monotonic_time")
        return warnings
    hrs = secs / 3600
    if km / hrs > max_kmh:
        warnings.append("implausible_speed")
    return warnings
