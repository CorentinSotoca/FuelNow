import json
from pathlib import Path

import pytest

from etl.adapters import OdsJsonAdapter
from etl.models import Fuel, Outage

FIXTURE = Path(__file__).parent / "fixtures" / "ods_sample.json"


@pytest.fixture()
def adapter() -> OdsJsonAdapter:
    data = json.loads(FIXTURE.read_text())
    return OdsJsonAdapter(data)


def test_total_records(adapter: OdsJsonAdapter):
    assert adapter.total_records == 8


def test_iter_stations_count(adapter: OdsJsonAdapter):
    stations = list(adapter.iter_stations())
    assert len(stations) == 6
    assert adapter.rejected_count == 2


def test_bad_geom_rejected(adapter: OdsJsonAdapter):
    stations = list(adapter.iter_stations())
    ids = [s.id for s in stations]
    assert 99999001 not in ids


def test_no_geom_rejected(adapter: OdsJsonAdapter):
    stations = list(adapter.iter_stations())
    ids = [s.id for s in stations]
    assert "no_geom" not in ids
    assert all(isinstance(s.id, int) for s in stations)


def test_bad_price_filtered(adapter: OdsJsonAdapter):
    stations = {s.id: s for s in adapter.iter_stations()}
    bad = stations[99999002]
    assert all(p.fuel != Fuel.gazole or p.price_eur is None for p in bad.prices)
    assert all(p.fuel != Fuel.sp95 or p.price_eur is None for p in bad.prices)


def test_station_fields(adapter: OdsJsonAdapter):
    stations = {s.id: s for s in adapter.iter_stations()}
    paris = stations[75001003]
    assert paris.city == "Paris"
    assert paris.road_type == "R"
    assert paris.postal_code == "75001"
    assert paris.lon == pytest.approx(2.3522)
    assert paris.lat == pytest.approx(48.8566)


def test_depivot_prices(adapter: OdsJsonAdapter):
    stations = {s.id: s for s in adapter.iter_stations()}
    paris = stations[75001003]

    fuels = {p.fuel for p in paris.prices}
    assert Fuel.gazole in fuels
    assert Fuel.sp95 in fuels
    assert Fuel.sp98 in fuels
    assert Fuel.e10 in fuels
    assert Fuel.e85 in fuels

    e85 = next(p for p in paris.prices if p.fuel == Fuel.e85)
    assert e85.price_eur is None
    assert e85.outage == Outage.temporary


def test_rupture_definitive(adapter: OdsJsonAdapter):
    stations = {s.id: s for s in adapter.iter_stations()}
    dargnies = stations[80570001]

    e10 = next(p for p in dargnies.prices if p.fuel == Fuel.e10)
    assert e10.outage == Outage.definitive
    assert e10.price_eur is None

    gplc = next(p for p in dargnies.prices if p.fuel == Fuel.gplc)
    assert gplc.outage == Outage.definitive


def test_drom_included(adapter: OdsJsonAdapter):
    stations = {s.id: s for s in adapter.iter_stations()}
    martinique = stations[97201004]
    assert martinique.lat == pytest.approx(14.6108)
    assert martinique.lon == pytest.approx(-60.9867)


def test_all_six_fuels(adapter: OdsJsonAdapter):
    stations = {s.id: s for s in adapter.iter_stations()}
    marseille = stations[13001005]
    fuels = {p.fuel for p in marseille.prices}
    assert fuels == {Fuel.gazole, Fuel.sp95, Fuel.sp98, Fuel.e10, Fuel.e85, Fuel.gplc}


def test_from_bytes_gzip():
    import gzip as gz
    raw = json.loads(FIXTURE.read_text())
    compressed = gz.compress(json.dumps(raw).encode())
    adapter = OdsJsonAdapter.from_bytes(compressed)
    assert adapter.total_records == 8


def test_from_bytes_plain_json():
    raw = FIXTURE.read_text().encode()
    adapter = OdsJsonAdapter.from_bytes(raw)
    assert adapter.total_records == 8


def test_no_price_no_outage_excluded(adapter: OdsJsonAdapter):
    stations = {s.id: s for s in adapter.iter_stations()}
    martinique = stations[97201004]
    assert len(martinique.prices) == 1
    assert martinique.prices[0].fuel == Fuel.gazole
