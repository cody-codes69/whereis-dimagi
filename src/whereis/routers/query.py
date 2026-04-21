"""Time-travel query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..services import history
from ..templating import templates
from ..utils import parse_iso_utc

router = APIRouter()


@router.get("/whereis/{identifier}", response_class=HTMLResponse)
def whereis_html(
    identifier: str,
    request: Request,
    at: str | None = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        when = parse_iso_utc(at)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"bad 'at' value: {at}") from e

    person = history.find_person(session, identifier)
    upd = None
    if person:
        upd = history.as_of(session, person, when) if when else history.last_known(session, person)
    return templates.TemplateResponse(
        request,
        "whereis.html",
        {
            "identifier": identifier,
            "at": at,
            "update": upd,
            "person_known": person is not None,
        },
    )


@router.get("/whereis.txt", response_class=PlainTextResponse)
def whereis_all_plain(session: Session = Depends(get_session)) -> str:
    updates = history.latest_per_person(session)
    lines = ["# whereis — latest known locations (UTC, tab-separated)"]
    for u in updates:
        where = f"{u.place.name} ({u.place.country_code})" if u.place else u.raw_input
        ts = u.observed_at.strftime("%Y-%m-%d %H:%M")
        lines.append(f"{u.person.identifier}\t{ts}\t{where}")
    return "\n".join(lines) + "\n"


def _iso_z(dt) -> str:
    """Render a naive-UTC datetime as ISO-8601 with a trailing 'Z', idempotently."""
    iso = dt.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    if iso.endswith("Z"):
        return iso
    return iso + "Z"


@router.get("/whereis.json")
def whereis_all_json(session: Session = Depends(get_session)) -> JSONResponse:
    updates = history.latest_per_person(session)
    return JSONResponse([
        {
            "identifier": u.person.identifier,
            "display_name": u.person.display_name,
            "observed_at": _iso_z(u.observed_at),
            "place": u.place.name if u.place else None,
            "country": u.place.country_code if u.place else None,
            "lat": u.lat,
            "lng": u.lng,
            "source": u.source,
            "warnings": list(u.warnings or []),
        }
        for u in updates
    ])
