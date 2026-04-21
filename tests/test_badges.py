from datetime import UTC, datetime, timedelta

from whereis.schemas import InboundMessage
from whereis.services.badges import compute_badges
from whereis.services.ingest import ingest


def _submit(client, ident, ts_iso, place):
    r = client.post("/updates", json=[[ident, ts_iso, place]])
    assert r.status_code == 200, r.text


def _ingest(session, ident, place, t):
    ingest(session, InboundMessage(identifier=ident, observed_at=t, raw_location=place, source="api"))


def test_badges_basic(session):
    t = datetime(2011, 5, 1, tzinfo=UTC)
    _ingest(session, "a@x.com", "Boston", t)
    _ingest(session, "a@x.com", "Boston", t + timedelta(days=1))
    _ingest(session, "a@x.com", "Boston", t + timedelta(days=2))

    _ingest(session, "b@x.com", "Boston", t)
    _ingest(session, "b@x.com", "Delhi", t + timedelta(days=1))
    _ingest(session, "b@x.com", "Cape Town", t + timedelta(days=2))

    badges = compute_badges(session)
    slugs = {b.slug: b for b in badges}
    assert slugs["most-distance"].winner == "b@x.com"
    assert slugs["biggest-homebody"].winner == "a@x.com"
    assert slugs["globe-trotter"].winner == "b@x.com"
    assert slugs["phantom"].winner in {"a@x.com", "b@x.com"}


def test_fastest_leg_ignores_sub_minute_legs(client):
    # Two back-to-back updates 10s apart would award cosmic km/h under the
    # old code. Now: skipped → badge still published but winner is a real
    # leg, with value below the sanity cap.
    _submit(client, "fast@dimagi.com", "2024-01-01 10:00:00", "Delhi")
    _submit(client, "fast@dimagi.com", "2024-01-01 10:00:10", "Seattle")
    _submit(client, "slow@dimagi.com", "2024-01-01 10:00:00", "Dodoma")
    _submit(client, "slow@dimagi.com", "2024-01-02 10:00:00", "Lusaka")
    badges = {b["slug"]: b for b in client.get("/badges.json").json()}
    red_eye = badges["red-eye-rocket"]
    speed = float(red_eye["value"].replace(",", "").split()[0])
    assert speed < 2500, red_eye
    assert red_eye["winner"] == "slow@dimagi.com"


def test_fastest_leg_ignores_implausible_speed_warnings(client):
    _submit(client, "warn@dimagi.com", "2024-01-01 10:00:00", "Delhi")
    _submit(client, "warn@dimagi.com", "2024-01-01 10:15:00", "Seattle")
    _submit(client, "warn@dimagi.com", "2024-01-02 10:15:00", "Dodoma")
    badges = {b["slug"]: b for b in client.get("/badges.json").json()}
    red_eye = badges["red-eye-rocket"]
    speed = float(red_eye["value"].replace(",", "").split()[0])
    assert speed < 2500


def test_phoenix_is_second_longest_gap(client):
    _submit(client, "comet@dimagi.com", "2024-01-01 10:00:00", "Dodoma")
    _submit(client, "comet@dimagi.com", "2024-02-10 10:00:00", "Lusaka")
    _submit(client, "comet@dimagi.com", "2024-02-11 10:00:00", "Kampala")
    _submit(client, "comet@dimagi.com", "2024-02-12 10:00:00", "Nairobi")

    _submit(client, "quiet@dimagi.com", "2024-01-01 10:00:00", "Dodoma")
    _submit(client, "quiet@dimagi.com", "2024-01-02 10:00:00", "Lusaka")
    _submit(client, "quiet@dimagi.com", "2024-02-20 10:00:00", "Cape Town")

    badges = {b["slug"]: b for b in client.get("/badges.json").json()}
    assert badges["phantom"]["winner"] == "quiet@dimagi.com"
    assert badges["phoenix"]["winner"] == "comet@dimagi.com"


def test_new_badges_present(client):
    client.post("/updates", json=[
        ["a@dimagi.com", "2024-01-01 10:00", "Dodoma"],
        ["a@dimagi.com", "2024-01-02 10:00", "Lusaka"],
        ["a@dimagi.com", "2024-01-03 10:00", "Dublin"],
        ["b@dimagi.com", "2024-01-01 10:00", "Delhi"],
        ["b@dimagi.com", "2024-01-10 10:00", "Kampala"],
    ])
    r = client.get("/badges.json")
    assert r.status_code == 200
    slugs = {b["slug"] for b in r.json()}
    assert {
        "most-distance", "biggest-homebody", "globe-trotter",
        "red-eye-rocket", "time-bender", "phantom",
        "groundhog-day", "jet-lagger", "equator-crosser", "phoenix",
    }.issubset(slugs)
