from datetime import UTC, datetime, timedelta

from whereis.services.validator import validate_physics


def test_no_prior_no_warning():
    assert validate_physics(None, None, None, 1.0, 2.0, datetime.now(tz=UTC)) == []


def test_implausible_speed():
    t0 = datetime(2011, 5, 19, 14, 0, tzinfo=UTC)
    # Delhi to Seattle in 15 minutes — impossible.
    warn = validate_physics(28.65, 77.23, t0, 47.6, -122.33, t0 + timedelta(minutes=15))
    assert "implausible_speed" in warn


def test_plausible_speed():
    t0 = datetime(2011, 5, 19, 14, 0, tzinfo=UTC)
    # Boston to Springfield MA in 2 hours — fine.
    warn = validate_physics(42.36, -71.06, t0, 42.10, -72.59, t0 + timedelta(hours=2))
    assert warn == []


def test_non_monotonic_time():
    t0 = datetime(2011, 5, 19, 14, 0, tzinfo=UTC)
    warn = validate_physics(42.36, -71.06, t0, 28.65, 77.23, t0 - timedelta(hours=1))
    assert "non_monotonic_time" in warn


def test_physics_enforce_returns_422(client, monkeypatch):
    from whereis.config import settings

    monkeypatch.setattr(settings, "physics_enforce", True)
    client.post("/updates", json=[["fast@dimagi.com", "2024-01-01 10:00", "Delhi"]])
    r = client.post("/updates", json=[["fast@dimagi.com", "2024-01-01 10:15", "Seattle"]])
    assert r.status_code == 422
    assert "implausible_speed" in r.json()["detail"]["warnings"]
