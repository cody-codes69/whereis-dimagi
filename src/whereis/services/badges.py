"""Creative badges computed from a person's update history.

Results are cached in-memory, keyed by a simple ``(count, max_id)`` stamp of
the ``location_updates`` table so they invalidate automatically whenever a
new row lands.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import LocationUpdate, Person
from .strategies import haversine_km


@dataclass(frozen=True)
class Badge:
    slug: str
    title: str
    description: str
    winner: str
    value: str

    def dict(self) -> dict:
        return asdict(self)


_CACHE: dict[tuple[int, int], list[Badge]] = {}


def _cache_key(session: Session) -> tuple[int, int]:
    row = session.execute(
        select(func.count(LocationUpdate.id), func.coalesce(func.max(LocationUpdate.id), 0))
    ).one()
    return (int(row[0] or 0), int(row[1] or 0))


# ---- primitives ---------------------------------------------------------


def _updates_for(session: Session, person: Person) -> list[LocationUpdate]:
    return list(
        session.scalars(
            select(LocationUpdate)
            .where(LocationUpdate.person_id == person.id, LocationUpdate.lat.is_not(None))
            .order_by(LocationUpdate.observed_at)
        ).all()
    )


def _distance_km(updates: list[LocationUpdate]) -> float:
    total = 0.0
    for a, b in zip(updates, updates[1:], strict=False):
        total += haversine_km(a.lat, a.lng, b.lat, b.lng)  # type: ignore[arg-type]
    return total


_MIN_LEG_SECONDS = 60
_SPEED_SANITY_CAP_KMH = 2500  # ~Mach 2; beyond this we're looking at clock noise.


def _fastest_leg_kmh(updates: list[LocationUpdate]) -> float:
    """Largest sane km/h across consecutive legs.

    Guards against two failure modes seen in live data:
    * Two updates landing microseconds apart (``observed_at = now()`` twice)
      which would divide by ~0 and award cosmic speeds.
    * Any leg the physics validator already tagged ``implausible_speed``
      (e.g. geocoding mix-ups) — those legs are excluded from awards.
    """
    best = 0.0
    for a, b in zip(updates, updates[1:], strict=False):
        if "implausible_speed" in (b.warnings or []):
            continue
        secs = (b.observed_at - a.observed_at).total_seconds()
        if secs < _MIN_LEG_SECONDS:
            continue
        km = haversine_km(a.lat, a.lng, b.lat, b.lng)  # type: ignore[arg-type]
        if km <= 0:
            continue
        speed = km / (secs / 3600)
        if speed > _SPEED_SANITY_CAP_KMH:
            continue
        best = max(best, speed)
    return best


def _homebody_ratio(updates: list[LocationUpdate], radius_km: float) -> float:
    if not updates:
        return 0.0
    cx = sum(u.lat for u in updates) / len(updates)  # type: ignore[union-attr]
    cy = sum(u.lng for u in updates) / len(updates)  # type: ignore[union-attr]
    near = sum(1 for u in updates if haversine_km(cx, cy, u.lat, u.lng) <= radius_km)  # type: ignore[arg-type]
    return near / len(updates)


def _longest_gap(updates: list[LocationUpdate]) -> timedelta:
    best = timedelta(0)
    for a, b in zip(updates, updates[1:], strict=False):
        gap = b.observed_at - a.observed_at
        if gap > best:
            best = gap
    return best


def _phoenix_return(updates: list[LocationUpdate]) -> timedelta:
    """Longest past silence a person *broke*.

    Previously this was tied to ``max(gaps)``, which made the
    Phantom and Phoenix winners collapse whenever the most-recent gap was
    also the longest. We use ``max(gaps[:-1])`` so Phoenix credits the
    second-longest gap — i.e. the person who reappeared after a record
    silence, not the person currently in the longest silence.
    """
    if len(updates) < 3:
        return timedelta(0)
    gaps = [b.observed_at - a.observed_at for a, b in zip(updates, updates[1:], strict=False)]
    return max(gaps[:-1])


def _groundhog_max(updates: list[LocationUpdate]) -> int:
    """Largest count of consecutive updates at the same place within 24h."""
    best = 0
    run = 0
    last: LocationUpdate | None = None
    for u in updates:
        if last and u.place_id == last.place_id and (u.observed_at - last.observed_at) <= timedelta(hours=24):
            run += 1
        else:
            run = 1
        best = max(best, run)
        last = u
    return best


def _jetlag_score(updates: list[LocationUpdate]) -> int:
    """Sum of absolute timezone-offset deltas (in hours) between consecutive updates.

    Uses the raw IANA timezone string from GeoNames; offsets are approximated
    by resolving each tz at the update's observation time.
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # pragma: no cover
        return 0

    hours = 0
    prev_offset: float | None = None
    for u in updates:
        if not (u.place and u.place.timezone):
            continue
        try:
            zi = ZoneInfo(u.place.timezone)
        except Exception:  # noqa: BLE001
            continue
        observed = u.observed_at.replace(tzinfo=UTC)
        offset = zi.utcoffset(observed)
        if offset is None:
            continue
        hrs = offset.total_seconds() / 3600
        if prev_offset is not None:
            hours += int(abs(hrs - prev_offset))
        prev_offset = hrs
    return hours


def _equator_crossings(updates: list[LocationUpdate]) -> int:
    n = 0
    for a, b in zip(updates, updates[1:], strict=False):
        if a.lat is None or b.lat is None:
            continue
        if (a.lat >= 0) != (b.lat >= 0):
            n += 1
    return n


# ---- top-level ----------------------------------------------------------


def _format_timedelta(td: timedelta) -> str:
    days = td.days
    hours = td.seconds // 3600
    return f"{days}d {hours}h"


def _compute(session: Session) -> list[Badge]:
    persons = session.scalars(select(Person)).all()
    stats: list[dict] = []
    for p in persons:
        ups = _updates_for(session, p)
        if not ups:
            continue
        countries = Counter(u.place.country_code for u in ups if u.place)
        tzs = Counter(u.place.timezone for u in ups if u.place and u.place.timezone)
        stats.append({
            "person": p,
            "distance": _distance_km(ups),
            "speed": _fastest_leg_kmh(ups),
            "homebody": _homebody_ratio(ups, settings.homebody_radius_km),
            "countries": len(countries),
            "timezones": len(tzs),
            "gap": _longest_gap(ups),
            "groundhog": _groundhog_max(ups),
            "jetlag": _jetlag_score(ups),
            "equator": _equator_crossings(ups),
            "phoenix": _phoenix_return(ups),
            "updates": len(ups),
        })
    if not stats:
        return []

    def winner(key: str, fmt):  # noqa: ANN001
        best = max(stats, key=lambda s: s[key])
        return best["person"].identifier, fmt(best[key])

    badges: list[Badge] = []

    i, v = winner("distance", lambda x: f"{x:,.0f} km")
    badges.append(Badge("most-distance", "Most Distance Covered",
                        "Summed great-circle distance across all updates.", i, v))
    i, v = winner("homebody", lambda x: f"{x*100:.0f}% within {settings.homebody_radius_km:.0f} km of centroid")
    badges.append(Badge("biggest-homebody", "Biggest Homebody",
                        "Highest share of updates near their centroid.", i, v))
    i, v = winner("countries", lambda x: f"{x} countries")
    badges.append(Badge("globe-trotter", "Globe Trotter",
                        "Most distinct countries visited.", i, v))
    i, v = winner("speed", lambda x: f"{x:,.0f} km/h")
    badges.append(Badge("red-eye-rocket", "Red-Eye Rocket",
                        "Fastest single leg between consecutive updates.", i, v))
    i, v = winner("timezones", lambda x: f"{x} timezones")
    badges.append(Badge("time-bender", "Time Bender",
                        "Most distinct IANA timezones touched.", i, v))
    i, v = winner("gap", _format_timedelta)
    badges.append(Badge("phantom", "Phantom",
                        "Longest stretch without a location update. Missing in action.", i, v))
    i, v = winner("groundhog", lambda x: f"{x} check-ins in 24h at one place")
    badges.append(Badge("groundhog-day", "Groundhog Day",
                        "Most re-check-ins at the same place within 24 hours.", i, v))
    i, v = winner("jetlag", lambda x: f"{x} hours of cumulative tz swing")
    badges.append(Badge("jet-lagger", "Jet-Lagger",
                        "Largest sum of absolute timezone-offset deltas.", i, v))
    i, v = winner("equator", lambda x: f"{x} crossings")
    badges.append(Badge("equator-crosser", "Equator Crosser",
                        "Most hemisphere changes between consecutive updates.", i, v))
    i, v = winner("phoenix", _format_timedelta)
    badges.append(Badge("phoenix", "The Phoenix",
                        "Reappeared after the longest Phantom silence.", i, v))
    return badges


def compute_badges(session: Session) -> list[Badge]:
    key = _cache_key(session)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    _CACHE.clear()
    result = _compute(session)
    _CACHE[key] = result
    return result
