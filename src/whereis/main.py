"""FastAPI app factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .data.loader import _create_schema
from .routers import api, badges, email, form, health, query, sms
from .routers import map as map_router

STATIC_DIR = Path(__file__).parent / "static"


def _configure_logging() -> None:
    """Surface ``whereis.*`` logs through uvicorn's default sink"""
    whereis_logger = logging.getLogger("whereis")
    whereis_logger.setLevel(logging.INFO)
    if whereis_logger.handlers:
        return
    for name in ("uvicorn", "uvicorn.error"):
        for h in logging.getLogger(name).handlers:
            whereis_logger.addHandler(h)
    # Leave ``propagate=True`` (default) so that if no uvicorn handlers
    # exist, Python's root/lastResort handler still prints the record.


@asynccontextmanager
async def _lifespan(_: FastAPI):
    _configure_logging()
    _create_schema()
    imap_task = None
    if settings.email_adapter == "imap":
        from .adapters.email_imap import poll_loop
        imap_task = asyncio.create_task(poll_loop())
    try:
        yield
    finally:
        if imap_task:
            imap_task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Whereis Dimagi",
        version="0.1.0",
        description="Low-bandwidth location tracker backed by GeoNames.",
        lifespan=_lifespan,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(form.router)
    app.include_router(api.router)
    app.include_router(query.router)
    app.include_router(sms.router)
    app.include_router(email.router)
    app.include_router(map_router.router)
    app.include_router(badges.router)
    app.include_router(health.router)
    return app


app = create_app()
