"""Disambiguation strategies when multiple places match.

Open/closed: add a new strategy by implementing ``MatchStrategy`` and
registering it in ``STRATEGIES``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from ..models import Place


@dataclass(frozen=True)
class LookupContext:
    last_lat: float | None = None
    last_lng: float | None = None


class MatchStrategy(Protocol):
    name: str

    def pick(self, candidates: list[Place], ctx: LookupContext) -> Place | None: ...


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class PopulationStrategy:
    name = "population"

    def pick(self, candidates: list[Place], ctx: LookupContext) -> Place | None:
        return max(candidates, key=lambda p: (p.population or 0, p.geonameid), default=None)


class ProximityStrategy:
    name = "proximity"

    def pick(self, candidates: list[Place], ctx: LookupContext) -> Place | None:
        if ctx.last_lat is None or ctx.last_lng is None:
            return PopulationStrategy().pick(candidates, ctx)
        return min(
            candidates,
            key=lambda p: haversine_km(ctx.last_lat, ctx.last_lng, p.lat, p.lng),  # type: ignore[arg-type]
            default=None,
        )


class FirstHitStrategy:
    name = "first"

    def pick(self, candidates: list[Place], ctx: LookupContext) -> Place | None:
        return candidates[0] if candidates else None


STRATEGIES: dict[str, MatchStrategy] = {
    s.name: s()  # type: ignore[operator]
    for s in (PopulationStrategy, ProximityStrategy, FirstHitStrategy)
}


def get_strategy(name: str | None) -> MatchStrategy:
    from .. import config as cfg
    requested = (name or cfg.settings.default_strategy).lower()
    return STRATEGIES.get(requested, STRATEGIES[cfg.settings.default_strategy])
