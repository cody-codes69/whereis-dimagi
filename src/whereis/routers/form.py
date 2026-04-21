"""GET/POST /  — lightweight HTML form for field check-ins."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..config import StrategyName, settings
from ..db import get_session
from ..schemas import InboundMessage
from ..services.ingest import ingest
from ..templating import templates
from ..utils import parse_iso_utc

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def get_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "form.html",
        {"result": None, "prefill": {}, "default_strategy": settings.default_strategy},
    )


@router.post("/", response_class=HTMLResponse)
def post_form(
    request: Request,
    identifier: str = Form(...),
    location: str = Form(...),
    observed_at: str | None = Form(default=None),
    strategy: StrategyName = Form(default=settings.default_strategy),
    session: Session = Depends(get_session),
) -> HTMLResponse:
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
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "result": upd,
            "prefill": {"identifier": identifier, "strategy": strategy},
            "default_strategy": settings.default_strategy,
        },
    )
