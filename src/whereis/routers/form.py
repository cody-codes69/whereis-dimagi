"""GET/POST /  — lightweight HTML form for field check-ins"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..config import StrategyName, settings
from ..db import get_session
from ..models import LocationUpdate
from ..schemas import InboundMessage
from ..services.ingest import ingest
from ..templating import templates
from ..utils import parse_iso_utc

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def get_form(
    request: Request,
    ok: int | None = None,
    ident: str | None = None,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Render a blank form. If ``?ok=<id>`` is present, show the card for that update."""
    result = session.get(LocationUpdate, ok) if ok else None
    # Keep the identifier primed for back-to-back check-ins by the same user;
    # everything else (location/time) stays blank.
    prefill = {"identifier": ident or ""}
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "result": result,
            "prefill": prefill,
            "default_strategy": settings.default_strategy,
        },
    )


@router.post("/")
def post_form(
    identifier: str = Form(...),
    location: str = Form(...),
    observed_at: str | None = Form(default=None),
    strategy: StrategyName = Form(default=settings.default_strategy),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        when = parse_iso_utc(observed_at) or datetime.now(tz=UTC)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"bad observed_at: {observed_at}") from e

    msg = InboundMessage(
        identifier=identifier,
        observed_at=when,
        raw_location=location,
        source="form",
    )
    upd = ingest(session, msg, strategy_name=strategy)
    # 303 "See Other" — RFC-specified PRG: tells the browser to fetch the Location
    # with GET, regardless of the original method. See the module docstring.
    return RedirectResponse(
        url=f"/?ok={upd.id}&ident={identifier}",
        status_code=303,
    )
