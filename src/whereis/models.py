"""SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Place(Base):
    __tablename__ = "places"

    geonameid: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    asciiname: Mapped[str] = mapped_column(String(200), index=True)
    alternatenames: Mapped[str] = mapped_column(Text, default="")
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    admin1: Mapped[str] = mapped_column(String(20), default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    population: Mapped[int] = mapped_column(Integer, default=0)
    timezone: Mapped[str] = mapped_column(String(40), default="")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    updates: Mapped[list[LocationUpdate]] = relationship(
        back_populates="person", cascade="all, delete-orphan", order_by="LocationUpdate.observed_at"
    )


class LocationUpdate(Base):
    __tablename__ = "location_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    raw_input: Mapped[str] = mapped_column(String(500))
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.geonameid"), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20))  # form|sms|email|api
    match_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    person: Mapped[Person] = relationship(back_populates="updates")
    place: Mapped[Place | None] = relationship()

    __table_args__ = (
        Index("ix_person_time", "person_id", "observed_at"),
        UniqueConstraint("person_id", "observed_at", "raw_input", name="uq_dupe_guard"),
    )
