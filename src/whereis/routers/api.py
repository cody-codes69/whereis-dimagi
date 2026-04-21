"""JSON API. Accepts either a single record, a list of records, or the
array-of-tuples format from the exercise brief: ``[[ident, time, loc], ...]``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import StrategyName, settings
from ..db import get_session
from ..models import LocationUpdate
from ..schemas import InboundMessage, LocationUpdateOut, PlaceOut
from ..security import require_shared_secret
from ..services.ingest import ingest_batch
from ..utils import parse_iso_utc

router = APIRouter(prefix="/updates", tags=["updates"])


class UpdateIn(BaseModel):
    identifier: str
    observed_at: datetime | None = None
    location: str
    display_name: str | None = None


def _to_out(upd: LocationUpdate) -> LocationUpdateOut:
    place = None
    if upd.place:
        place = PlaceOut(
            geonameid=upd.place.geonameid,
            name=upd.place.name,
            country_code=upd.place.country_code,
            admin1=upd.place.admin1,
            lat=upd.place.lat,
            lng=upd.place.lng,
            population=upd.place.population,
            timezone=upd.place.timezone,
        )
    return LocationUpdateOut(
        id=upd.id,
        identifier=upd.person.identifier,
        display_name=upd.person.display_name,
        observed_at=upd.observed_at,
        raw_input=upd.raw_input,
        place=place,
        lat=upd.lat,
        lng=upd.lng,
        source=upd.source,
        match_confidence=upd.match_confidence,
        warnings=list(upd.warnings or []),
    )


Payload = Annotated[
    list[UpdateIn] | UpdateIn | list[list[Any]],
    Body(...),
]


def _to_messages(payload: list[UpdateIn] | UpdateIn | list[list[Any]]) -> list[InboundMessage]:
    if isinstance(payload, UpdateIn):
        payload = [payload]
    messages: list[InboundMessage] = []
    for p in payload:
        if isinstance(p, UpdateIn):
            when = p.observed_at or datetime.now(tz=UTC)
            messages.append(InboundMessage(
                identifier=p.identifier,
                observed_at=when,
                raw_location=p.location,
                source="api",
                display_name=p.display_name,
            ))
        elif isinstance(p, (list, tuple)) and len(p) == 3:
            ident, t, loc = p
            try:
                when = parse_iso_utc(str(t)) or datetime.now(tz=UTC)
            except (ValueError, TypeError) as e:
                raise HTTPException(400, f"bad time: {t}") from e
            messages.append(InboundMessage(
                identifier=str(ident),
                observed_at=when,
                raw_location=str(loc),
                source="api",
            ))
        else:
            raise HTTPException(400, f"unsupported item: {p!r}")
    return messages


@router.post(
    "",
    response_model=list[LocationUpdateOut],
    dependencies=[Depends(require_shared_secret)],
)
def post_updates(
    payload: Payload,
    strategy: StrategyName = Query(settings.default_strategy),
    session: Session = Depends(get_session),
) -> list[LocationUpdateOut]:
    messages = _to_messages(payload)
    updates = ingest_batch(session, messages, strategy_name=strategy)
    return [_to_out(u) for u in updates]
