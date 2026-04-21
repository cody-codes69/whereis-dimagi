"""GET /healthz — cheap liveness probe for compose/CI."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import LocationUpdate, Person, Place

router = APIRouter()


@router.get("/healthz")
def healthz(session: Session = Depends(get_session)) -> dict:
    places = session.scalar(select(func.count(Place.geonameid))) or 0
    people = session.scalar(select(func.count(Person.id))) or 0
    updates = session.scalar(select(func.count(LocationUpdate.id))) or 0
    return {
        "status": "ok" if places > 0 else "seed_required",
        "places_count": int(places),
        "people_count": int(people),
        "updates_count": int(updates),
        "sms_adapter": settings.sms_adapter,
        "email_adapter": settings.email_adapter,
        "default_strategy": settings.default_strategy,
    }
