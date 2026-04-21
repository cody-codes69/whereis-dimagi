from datetime import datetime


def test_end_to_end_physics_warning(client):
    # Delhi then Seattle 15 min later → implausible.
    client.post("/updates", json=[["sonic@dimagi.com", "2011-05-19 14:00", "Delhi"]])
    r = client.post("/updates", json=[["sonic@dimagi.com", "2011-05-19 14:15", "Seattle"]])
    assert r.status_code == 200
    warnings = r.json()[0]["warnings"]
    assert "implausible_speed" in warnings


def _install_fake_httpx_client(monkeypatch, captured: dict) -> None:
    import httpx

    _RealClient = httpx.Client

    class _Transport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            captured["headers"] = dict(request.headers)
            captured["path"] = request.url.path
            return httpx.Response(200, json={"ok": True})

    def _fake_client(*args, **kwargs):
        kwargs["transport"] = _Transport()
        return _RealClient(*args, **kwargs)

    from whereis.tools import generate_fixtures as gf

    monkeypatch.setattr(gf.httpx, "Client", _fake_client)


def test_loader_drops_rtree_leftovers(tmp_path, monkeypatch):
    import sqlite3

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import whereis.db as db_mod
    from whereis import config as cfg_mod

    db_file = tmp_path / "legacy.db"
    cx = sqlite3.connect(db_file)
    cx.executescript(
        """
        CREATE VIRTUAL TABLE places_rtree USING rtree(id, minLat, maxLat, minLng, maxLng);
        INSERT INTO places_rtree(id, minLat, maxLat, minLng, maxLng) VALUES (1, 0, 0, 0, 0);
        """
    )
    cx.close()

    monkeypatch.setattr(cfg_mod.settings, "db_path", db_file)
    monkeypatch.setattr(
        db_mod,
        "engine",
        create_engine(
            f"sqlite:///{db_file}",
            future=True,
            connect_args={"check_same_thread": False},
        ),
    )
    monkeypatch.setattr(
        db_mod,
        "SessionLocal",
        sessionmaker(bind=db_mod.engine, autoflush=False, expire_on_commit=False),
    )

    from whereis.data.loader import _create_schema

    _create_schema()

    cx = sqlite3.connect(db_file)
    tables = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cx.close()
    assert not any(t.startswith("places_rtree") for t in tables), tables


def test_fixture_generator_includes_shared_secret(monkeypatch):
    monkeypatch.setenv("WHEREIS_SHARED_SECRET", "super-secret")
    monkeypatch.delenv("WHEREIS_TWILIO_VERIFY_SIGNATURE", raising=False)

    captured: dict = {}
    _install_fake_httpx_client(monkeypatch, captured)

    from whereis.schemas import InboundMessage
    from whereis.tools.generate_fixtures import _post_to

    msg = InboundMessage(
        identifier="alice@dimagi.com",
        observed_at=datetime(2024, 1, 1, 10, 0),
        raw_location="Dodoma",
        source="form",
    )
    _post_to("http://fake-target", msg)
    assert captured["headers"].get("x-shared-secret") == "super-secret"


def test_fixture_generator_signs_twilio_sms(monkeypatch):
    monkeypatch.setenv("WHEREIS_TWILIO_AUTH_TOKEN", "t0k3n")
    monkeypatch.setenv("WHEREIS_TWILIO_VERIFY_SIGNATURE", "true")
    monkeypatch.delenv("WHEREIS_SHARED_SECRET", raising=False)

    captured: dict = {}
    _install_fake_httpx_client(monkeypatch, captured)

    from whereis.schemas import InboundMessage
    from whereis.tools.generate_fixtures import _post_to, _twilio_signature

    msg = InboundMessage(
        identifier="+15551234567",
        observed_at=datetime(2024, 1, 1, 10, 0),
        raw_location="Dodoma",
        source="sms",
    )
    _post_to("http://fake-target", msg)
    sig_header = captured["headers"].get("x-twilio-signature")
    assert sig_header, captured["headers"]

    expected = _twilio_signature(
        "http://fake-target/webhooks/sms",
        {"From": "+15551234567", "Body": "Dodoma"},
        "t0k3n",
    )
    assert sig_header == expected


def test_end_to_end_map_and_badges(client):
    client.post("/updates", json=[["nick@dimagi.com", "2011-05-01 10:00", "Dodoma"]])
    client.post("/updates", json=[["nick@dimagi.com", "2011-05-15 10:00", "Lusaka"]])
    r = client.get("/map")
    assert r.status_code == 200
    assert "nick@dimagi.com" in r.text or "Lusaka" in r.text

    r2 = client.get("/badges.json")
    assert r2.status_code == 200
    slugs = {b["slug"] for b in r2.json()}
    assert {"most-distance", "globe-trotter", "phantom"}.issubset(slugs)
