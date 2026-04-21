"""GET /map — Leaflet map with graceful fallback."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..services import history
from ..templating import templates
from ..utils import parse_iso_utc

router = APIRouter()


@router.get("/map", response_class=HTMLResponse)
def map_view(
    request: Request,
    at: str | None = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        when = parse_iso_utc(at)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"bad 'at' value: {at}") from e

    updates = history.latest_per_person(session, when=when)
    pins = [
        {
            "identifier": u.person.identifier,
            "identifier_url": quote(u.person.identifier, safe=""),
            "lat": u.lat,
            "lng": u.lng,
            "where": (u.place.name + ", " + u.place.country_code) if u.place else u.raw_input,
            "observed_at": u.observed_at.isoformat(),
        }
        for u in updates
        if u.lat is not None and u.lng is not None
    ]
    return templates.TemplateResponse(
        request, "map.html", {"pins": pins, "at": at}
    )
