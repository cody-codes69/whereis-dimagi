"""Test fixtures.

* Use an on-disk SQLite file (not ``:memory:``) so FTS5 behaves identically
  to production.
* Use FastAPI's ``dependency_overrides`` to rebind the session dependency —
  cleaner and more robust than rebinding module globals.
"""

from __future__ import annotations

import os

import pytest

# -- 1. Purge every WHEREIS_* env var inherited from a local .env and force
#       safe defaults BEFORE any whereis.* import sees them.

for k in list(os.environ):
    if k.startswith("WHEREIS_"):
        del os.environ[k]

os.environ["WHEREIS_SMS_ADAPTER"] = "simulator"
os.environ["WHEREIS_EMAIL_ADAPTER"] = "simulator"
os.environ["WHEREIS_TWILIO_VERIFY_SIGNATURE"] = "false"
os.environ["WHEREIS_PHYSICS_ENFORCE"] = "false"
os.environ["WHEREIS_SHARED_SECRET"] = ""  # disable the gate in tests


TEST_PLACES = [
    # (geonameid, name, asciiname, alternatenames, country, admin1, lat, lng, pop, tz)
    (1, "Dodoma", "Dodoma", "", "TZ", "03", -6.17, 35.74, 410956, "Africa/Dar_es_Salaam"),
    (2, "Lusaka", "Lusaka", "", "ZM", "09", -15.41, 28.28, 1267440, "Africa/Lusaka"),
    (3, "Boston", "Boston", "Bean Town", "US", "MA", 42.36, -71.06, 617594, "America/New_York"),
    (4, "Boston", "Boston", "", "GB", "ENG", 52.97, -0.02, 35124, "Europe/London"),
    (5, "Delhi", "Delhi", "New Delhi", "IN", "07", 28.65, 77.23, 10927986, "Asia/Kolkata"),
    (6, "Cape Town", "Cape Town", "", "ZA", "11", -33.92, 18.42, 3433504, "Africa/Johannesburg"),
    (7, "Bhopal", "Bhopal", "", "IN", "35", 23.25, 77.41, 1599914, "Asia/Kolkata"),
    (8, "Kampala", "Kampala", "", "UG", "C", 0.31, 32.58, 1353189, "Africa/Kampala"),
    (9, "Maputo", "Maputo", "", "MZ", "04", -25.97, 32.58, 1191613, "Africa/Maputo"),
    (10, "Dakar", "Dakar", "", "SN", "01", 14.69, -17.44, 2476400, "Africa/Dakar"),
    (11, "Nairobi", "Nairobi", "", "KE", "110", -1.28, 36.82, 2750547, "Africa/Nairobi"),
    (12, "Dublin", "Dublin", "", "IE", "07", 53.33, -6.25, 1024027, "Europe/Dublin"),
    (13, "Amsterdam", "Amsterdam", "", "NL", "07", 52.37, 4.89, 741636, "Europe/Amsterdam"),
    (14, "Trondheim", "Trondheim", "", "NO", "16", 63.43, 10.39, 147139, "Europe/Oslo"),
    (15, "Springfield", "Springfield", "", "US", "MO", 37.21, -93.29, 166810, "America/Chicago"),
    (16, "Springfield", "Springfield", "", "US", "MA", 42.10, -72.59, 153060, "America/New_York"),
    (17, "Springfield", "Springfield", "", "US", "IL", 39.80, -89.64, 114230, "America/Chicago"),
    (18, "San Francisco", "San Francisco", "", "US", "CA", 37.77, -122.42, 864816, "America/Los_Angeles"),
    (19, "San Diego", "San Diego", "", "US", "CA", 32.72, -117.16, 1394928, "America/Los_Angeles"),
    (20, "Seattle", "Seattle", "", "US", "WA", 47.60, -122.33, 744955, "America/Los_Angeles"),
    (21, "Bangkok", "Bangkok", "Krung Thep", "TH", "40", 13.75, 100.50, 5104476, "Asia/Bangkok"),
    (22, "Pondicherry", "Pondicherry", "Puducherry", "IN", "28", 11.93, 79.83, 241773, "Asia/Kolkata"),
]


@pytest.fixture(scope="session", autouse=True)
def _test_db(tmp_path_factory):
    """Rebuild settings + engine + session factory against a temp DB."""
    tmp = tmp_path_factory.mktemp("whereis")
    db_path = tmp / "whereis.test.db"
    os.environ["WHEREIS_DB_PATH"] = str(db_path)

    # Force settings to re-read env, then rebuild the engine that the app
    # imports lazily. We use ``_env_file=None`` to belt-and-brace against a
    # stray .env in the repo root.
    from whereis import config as cfg_mod
    cfg_mod.settings = cfg_mod.Settings(_env_file=None)  # type: ignore[call-arg]

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    import whereis.db as db_mod

    db_mod.engine.dispose()
    db_mod.engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(db_mod.engine, "connect")
    def _on(c, _):  # noqa: ANN001
        cur = c.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
        c.create_function("REGEXP", 2, db_mod._regexp)

    db_mod.SessionLocal = sessionmaker(
        bind=db_mod.engine, autoflush=False, expire_on_commit=False
    )

    from whereis.data.loader import _create_schema
    _create_schema()
    with db_mod.raw_connection() as cx:
        cx.execute("DELETE FROM places")
        cx.execute("DELETE FROM places_fts")
        for row in TEST_PLACES:
            cx.execute(
                "INSERT INTO places (geonameid, name, asciiname, alternatenames, country_code, admin1, lat, lng, population, timezone) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            cx.execute(
                "INSERT INTO places_fts(rowid, name, asciiname, alternatenames) VALUES (?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3]),
            )
        cx.commit()
    yield db_path


@pytest.fixture()
def session():
    from whereis.db import SessionLocal
    with SessionLocal() as s:
        yield s


@pytest.fixture(autouse=True)
def _clear_users():
    """Remove persons + updates between tests but keep the places seed."""
    yield
    from whereis.db import raw_connection
    with raw_connection() as cx:
        cx.execute("DELETE FROM location_updates")
        cx.execute("DELETE FROM persons")
        cx.commit()
    # Also clear badge cache between tests.
    from whereis.services import badges
    badges._CACHE.clear()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from whereis.db import SessionLocal, get_session
    from whereis.main import app

    def _override():
        with SessionLocal() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_session, None)
