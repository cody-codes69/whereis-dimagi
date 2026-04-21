from dataclasses import dataclass

from whereis.services.strategies import (
    FirstHitStrategy,
    LookupContext,
    PopulationStrategy,
    ProximityStrategy,
    get_strategy,
    haversine_km,
)


@dataclass
class P:
    geonameid: int
    name: str
    lat: float
    lng: float
    population: int


def test_population_pick_largest():
    cs = [P(1, "A", 0, 0, 100), P(2, "B", 0, 0, 500), P(3, "C", 0, 0, 250)]
    out = PopulationStrategy().pick(cs, LookupContext())
    assert out.geonameid == 2


def test_proximity_picks_closest_to_last_known():
    cs = [P(1, "Far", 10, 10, 1), P(2, "Near", 0.1, 0.1, 1)]
    out = ProximityStrategy().pick(cs, LookupContext(last_lat=0, last_lng=0))
    assert out.geonameid == 2


def test_proximity_falls_back_to_population_when_no_context():
    cs = [P(1, "Small", 0, 0, 1), P(2, "Big", 50, 50, 999)]
    out = ProximityStrategy().pick(cs, LookupContext())
    assert out.geonameid == 2


def test_first_hit():
    cs = [P(1, "A", 0, 0, 1), P(2, "B", 0, 0, 2)]
    assert FirstHitStrategy().pick(cs, LookupContext()).geonameid == 1


def test_get_strategy_default():
    assert get_strategy(None).name == "population"
    assert get_strategy("proximity").name == "proximity"
    assert get_strategy("bogus").name == "population"


def test_haversine_sanity():
    # NYC to London ~ 5570 km
    d = haversine_km(40.71, -74.01, 51.51, -0.13)
    assert 5400 < d < 5700


def test_strategy_name_reexported_from_schemas():
    from whereis.config import StrategyName as Cfg
    from whereis.schemas import StrategyName as Sch

    assert Cfg is Sch
