from __future__ import annotations

from etl.osm import OverpassAdapter, overpass_endpoints


def _node(osm_id: int, lat: float, lon: float, tags: dict) -> dict:
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": tags}


def test_parse_node_with_ref_brand_and_name():
    adapter = OverpassAdapter([
        _node(1, 48.85, 2.35, {
            "brand": "TotalEnergies",
            "name": "TotalEnergies Paris Bastille",
            "ref:FR:prix-carburants": "5900001",
        }),
    ])
    records = adapter.parse()
    assert len(records) == 1
    r = records[0]
    assert r.osm_type == "node"
    assert r.osm_id == 1
    assert r.station_ref == 5900001
    assert r.brand == "TotalEnergies"
    assert r.osm_name == "TotalEnergies Paris Bastille"
    assert (r.lat, r.lon) == (48.85, 2.35)


def test_parse_multi_ref_emits_one_record_per_ref():
    adapter = OverpassAdapter([
        _node(2, 48.0, 2.0, {"brand": "Esso", "ref:FR:prix-carburants": "4500001;4500002"}),
    ])
    records = adapter.parse()
    assert len(records) == 2
    assert {r.station_ref for r in records} == {4500001, 4500002}
    assert all(r.osm_id == 2 for r in records)


def test_parse_invalid_ref_falls_back_to_no_ref():
    adapter = OverpassAdapter([
        _node(3, 48.0, 2.0, {"brand": "Esso", "ref:FR:prix-carburants": "abc"}),
    ])
    records = adapter.parse()
    assert len(records) == 1
    assert records[0].station_ref is None


def test_parse_no_ref_yields_single_record_without_ref():
    adapter = OverpassAdapter([_node(4, 48.0, 2.0, {"name": "Station Sans Ref"})])
    records = adapter.parse()
    assert len(records) == 1
    assert records[0].station_ref is None
    assert records[0].brand is None
    assert records[0].osm_name == "Station Sans Ref"


def test_parse_skips_poi_without_brand_and_name():
    adapter = OverpassAdapter([_node(5, 48.0, 2.0, {"ref:FR:prix-carburants": "5900001"})])
    assert adapter.parse() == []


def test_parse_way_uses_center_coordinates():
    adapter = OverpassAdapter([
        {
            "type": "way",
            "id": 6,
            "center": {"lat": 45.75, "lon": 4.85},
            "tags": {"brand": "TotalEnergies", "name": "Total A7"},
        },
    ])
    records = adapter.parse()
    assert len(records) == 1
    assert records[0].osm_type == "way"
    assert (records[0].lat, records[0].lon) == (45.75, 4.85)


def test_parse_skips_element_without_coordinates():
    # way sans centre (ni lat/lon directes) → inexploitable
    adapter = OverpassAdapter([
        {"type": "way", "id": 7, "tags": {"brand": "Esso"}},
    ])
    assert adapter.parse() == []


def test_parse_strips_and_normalizes_empty_strings():
    adapter = OverpassAdapter([
        _node(8, 48.0, 2.0, {"brand": "  Leclerc  ", "name": "   "}),
    ])
    records = adapter.parse()
    assert len(records) == 1
    assert records[0].brand == "Leclerc"
    assert records[0].osm_name is None


def test_parse_ignores_unexpected_element_type():
    adapter = OverpassAdapter([
        {"type": "bounds", "id": 9, "lat": 48.0, "lon": 2.0, "tags": {"brand": "X"}},
    ])
    assert adapter.parse() == []


def test_overpass_endpoints_splits_and_trims():
    assert overpass_endpoints(" a.com , b.com ,, ") == ["a.com", "b.com"]
