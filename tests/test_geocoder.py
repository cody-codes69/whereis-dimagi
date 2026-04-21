from whereis.services.geocoder import geocode
from whereis.services.strategies import (
    FirstHitStrategy,
    LookupContext,
    PopulationStrategy,
    ProximityStrategy,
)


def test_exact_match(session):
    m = geocode(session, "Dodoma", LookupContext(), PopulationStrategy())
    assert m.place is not None
    assert m.place.name == "Dodoma"
    assert m.confidence == 1.0


def test_partial_match_via_fts(session):
    m = geocode(session, "Dod", LookupContext(), PopulationStrategy())
    assert m.place is not None
    assert m.place.name == "Dodoma"


def test_fuzzy_match(session):
    m = geocode(session, "Dodomma", LookupContext(), PopulationStrategy())  # typo
    assert m.place is not None
    assert m.place.name == "Dodoma"


def test_regex_match(session):
    m = geocode(session, "/^San .*/", LookupContext(), FirstHitStrategy())
    assert m.place is not None
    assert m.place.name.startswith("San")


def test_disambiguation_by_population(session):
    m = geocode(session, "Boston", LookupContext(), PopulationStrategy())
    assert m.place.country_code == "US"  # US Boston has larger population


def test_disambiguation_by_proximity(session):
    # From Springfield IL, the closest "Springfield" should be itself.
    # From Boston MA (~42.36, -71.06), closest Springfield should be MA.
    ctx = LookupContext(last_lat=42.36, last_lng=-71.06)
    m = geocode(session, "Springfield", ctx, ProximityStrategy())
    assert m.place.admin1 == "MA"


def test_no_match(session):
    m = geocode(session, "Zzzzzzzzzz", LookupContext(), PopulationStrategy())
    assert m.place is None


def test_regex_search_prefers_high_population(client):
    r = client.post("/updates", json=[["rx@dimagi.com", "2024-01-01 10:00:00", "/^Boston$/"]])
    assert r.status_code == 200
    row = r.json()[0]
    assert row["place"]["name"] == "Boston"
    assert row["place"]["country_code"] == "US"


def test_fuzzy_match_confidence_reflects_score(client):
    r = client.post("/updates", json=[["fuzz@dimagi.com", "2024-01-01 10:00", "Dodomaa"]])
    assert r.status_code == 200
    row = r.json()[0]
    assert row["place"] is not None
    assert 0.5 <= row["match_confidence"] < 0.85


def test_regex_search_limits_scan(client):
    r = client.post("/updates", json=[["regex@dimagi.com", "2024-01-01 10:00", "/^Spring.*/"]])
    assert r.status_code == 200
    assert r.json()[0]["place"]["name"] == "Springfield"
