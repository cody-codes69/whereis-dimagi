"""Pydantic DTOs used across routers and adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .config import StrategyName  # re-exported for existing callers

__all__ = ["InboundMessage", "PlaceOut", "LocationUpdateOut", "Source", "StrategyName"]

Source = Literal["form", "sms", "email", "api"]


class InboundMessage(BaseModel):
    """Common DTO produced by every adapter (form, SMS, email)."""

    identifier: str = Field(..., description="Email or E.164 phone number.")
    observed_at: datetime
    raw_location: str
    source: Source = "form"
    display_name: str | None = None


class PlaceOut(BaseModel):
    geonameid: int
    name: str
    country_code: str
    admin1: str = ""
    lat: float
    lng: float
    population: int = 0
    timezone: str = ""


class LocationUpdateOut(BaseModel):
    id: int
    identifier: str
    display_name: str | None = ""
    observed_at: datetime
    raw_input: str
    place: PlaceOut | None = None
    lat: float | None = None
    lng: float | None = None
    source: Source
    match_confidence: float
    warnings: list[str] = []
