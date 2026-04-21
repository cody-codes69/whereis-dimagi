"""GET /badges — creative awards leaderboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..services.badges import compute_badges
from ..templating import templates

router = APIRouter()


@router.get("/badges", response_class=HTMLResponse)
def badges_view(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    badges = compute_badges(session)
    return templates.TemplateResponse(request, "badges.html", {"badges": badges})


@router.get("/badges.json")
def badges_json(session: Session = Depends(get_session)) -> list[dict]:
    return [b.__dict__ for b in compute_badges(session)]
