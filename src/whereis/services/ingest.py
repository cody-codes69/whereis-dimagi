"""Single entry point used by every transport (form / api / sms / email).

Takes an ``InboundMessage``, looks up the place, validates physics, stores
the normalized ``LocationUpdate`` and returns it.

Two public shapes:

* ``ingest(session, msg)`` — commits immediately. Convenient for single-row
  transports (form, webhook).
* ``ingest_batch(session, msgs)`` — flushes per-row and commits once. Use for
  the JSON ``/updates`` batch endpoint to avoid N fsyncs.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import config as _config_mod
from ..models import LocationUpdate, Person
from ..schemas import InboundMessage
from ..utils import derive_display_name, to_naive_utc
from .geocoder import geocode
from .history import find_person, last_known
from .strategies import LookupContext, get_strategy
from .validator import validate_physics


class PhysicsRejected(HTTPException):
    """Raised when PHYSICS_ENFORCE=true and an update implies impossible travel."""

    def __init__(self, warnings: list[str]):
        super().__init__(status_code=422, detail={"warnings": warnings})


def _get_or_create_person(session: Session, msg: InboundMessage) -> Person:
    person = find_person(session, msg.identifier)
    if person is None:
        person = Person(
            identifier=msg.identifier,
            display_name=msg.display_name or derive_display_name(msg.identifier),
        )
        session.add(person)
        session.flush()
    elif msg.display_name and not person.display_name:
        person.display_name = msg.display_name
    return person


def _build_update(session: Session, msg: InboundMessage, strategy_name: str | None) -> LocationUpdate:
    person = _get_or_create_person(session, msg)

    prev = last_known(session, person)
    ctx = LookupContext(
        last_lat=prev.lat if prev else None,
        last_lng=prev.lng if prev else None,
    )
    strategy = get_strategy(strategy_name or _config_mod.settings.default_strategy)

    match = geocode(session, msg.raw_location, ctx, strategy)
    place = match.place

    new_time = to_naive_utc(msg.observed_at)
    warnings = validate_physics(
        prev_lat=prev.lat if prev else None,
        prev_lng=prev.lng if prev else None,
        prev_time=prev.observed_at if prev else None,
        new_lat=place.lat if place else None,
        new_lng=place.lng if place else None,
        new_time=new_time,
    )
    if not place:
        warnings.append("unmatched_place")

    if _config_mod.settings.physics_enforce and "implausible_speed" in warnings:
        raise PhysicsRejected(warnings)

    upd = LocationUpdate(
        person_id=person.id,
        observed_at=new_time,
        raw_input=msg.raw_location,
        place_id=place.geonameid if place else None,
        lat=place.lat if place else None,
        lng=place.lng if place else None,
        source=msg.source,
        match_confidence=match.confidence,
        warnings=warnings,
    )
    session.add(upd)
    return upd


def ingest(
    session: Session,
    msg: InboundMessage,
    strategy_name: str | None = None,
) -> LocationUpdate:
    upd = _build_update(session, msg, strategy_name)
    session.commit()
    session.refresh(upd)
    return upd


def ingest_batch(
    session: Session,
    msgs: Iterable[InboundMessage],
    strategy_name: str | None = None,
) -> list[LocationUpdate]:
    updates: list[LocationUpdate] = []
    for m in msgs:
        updates.append(_build_update(session, m, strategy_name))
        session.flush()
    session.commit()
    for u in updates:
        session.refresh(u)
    return updates
