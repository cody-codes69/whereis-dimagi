from datetime import UTC, datetime


def test_healthz_reports_counts(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["places_count"] >= 20
    assert body["sms_adapter"] == "simulator"


def test_whereis_json(client):
    client.post("/updates", json=[["alice@dimagi.com", "2024-01-01 10:00", "Dodoma"]])
    r = client.get("/whereis.json")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["identifier"] == "alice@dimagi.com"
    assert rows[0]["place"] == "Dodoma"
    assert rows[0]["country"] == "TZ"


def test_whereis_json_observed_at_ends_in_single_z(client):
    client.post("/updates", json=[["iso@dimagi.com", "2024-01-01 10:00:00", "Dodoma"]])
    row = client.get("/whereis.json").json()[0]
    ts = row["observed_at"]
    assert ts.endswith("Z"), ts
    assert ts.count("Z") == 1
    assert "+00:00" not in ts


def test_whereis_json_handles_tz_aware():
    from whereis.routers.query import _iso_z

    naive = datetime(2024, 1, 1, 10, 0, tzinfo=None)
    assert _iso_z(naive).endswith("Z")
    aware = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    assert _iso_z(aware).endswith("Z")
    assert "+00:00" not in _iso_z(aware)


def test_unknown_person_has_meta_tag(client):
    r = client.get("/whereis/ghost@nowhere.example")
    assert r.status_code == 200
    assert 'name="whereis-status" content="unknown"' in r.text


def test_as_of_returns_most_recent_leq(client):
    client.post("/updates", json=[["nick@dimagi.com", "2011-05-01 10:00", "Dodoma"]])
    client.post("/updates", json=[["nick@dimagi.com", "2011-06-01 10:00", "Lusaka"]])
    client.post("/updates", json=[["nick@dimagi.com", "2011-07-01 10:00", "Cape Town"]])

    r = client.get("/whereis/nick@dimagi.com", params={"at": "2011-06-15T00:00:00Z"})
    assert r.status_code == 200
    assert "Lusaka" in r.text
    assert "Cape Town" not in r.text


def test_as_of_before_first_update_empty(client):
    client.post("/updates", json=[["x@y.com", "2026-01-01 00:00", "Delhi"]])
    r = client.get("/whereis/x@y.com", params={"at": "2020-01-01T00:00:00Z"})
    assert r.status_code == 200
    assert "No updates found" in r.text
