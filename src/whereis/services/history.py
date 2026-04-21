"""Read helpers for location history (as-of queries, most-recent lookups)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LocationUpdate, Person


def find_person(session: Session, identifier: str) -> Person | None:
    return session.scalar(
        select(Person).where(Person.identifier == identifier.strip().lower())
    )


def last_known(session: Session, person: Person) -> LocationUpdate | None:
    return session.scalar(
        select(LocationUpdate)
        .where(LocationUpdate.person_id == person.id)
        .order_by(LocationUpdate.observed_at.desc())
        .limit(1)
    )


def as_of(session: Session, person: Person, when: datetime) -> LocationUpdate | None:
    return session.scalar(
        select(LocationUpdate)
        .where(LocationUpdate.person_id == person.id, LocationUpdate.observed_at <= when)
        .order_by(LocationUpdate.observed_at.desc())
        .limit(1)
    )


def latest_per_person(session: Session, when: datetime | None = None) -> list[LocationUpdate]:
    """Return one LocationUpdate per person — the most recent <= `when`."""
    people = session.scalars(select(Person)).all()
    out: list[LocationUpdate] = []
    for p in people:
        upd = as_of(session, p, when) if when else last_known(session, p)
        if upd is not None:
            out.append(upd)
    return out
