from __future__ import annotations

from unittest.mock import patch

import httpx

from etl.osm import OverpassAdapter, overpass_endpoints

# Capturé à l'import, avant tout patch : la factory ci-dessous remplace
# httpx.AsyncClient et ne doit pas s'appeler elle-même.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(handler):
    def factory(**kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs)
    return factory


async def test_fetch_rejects_partial_results_with_remark():
    # Un endpoint renvoie 200 + remark (résultats partiels Overpass) → on
    # bascule sur l'endpoint suivant, qui répond sainement.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.test":
            return httpx.Response(200, json={
                "remark": "runtime error: Query timed out",
                "elements": [{"type": "node", "id": 1, "lat": -17.0, "lon": -149.0, "tags": {"brand": "Total"}}],
            })
        return httpx.Response(200, json={
            "elements": [{"type": "node", "id": 2, "lat": 48.0, "lon": 2.0, "tags": {"brand": "Esso"}}],
        })

    with patch("etl.osm.httpx.AsyncClient", _client_factory(handler)):
        adapter = await OverpassAdapter.fetch(
            ["https://a.test/api/interpreter", "https://b.test/api/interpreter"],
            timeout=5.0,
        )
    assert adapter.total_elements == 1
    assert adapter.parse()[0].osm_id == 2


async def test_fetch_falls_back_on_client_error():
    # 406 (overpass-api.de sans UA identifiant) → endpoint suivant.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.test":
            return httpx.Response(406, text="Not Acceptable")
        return httpx.Response(200, json={
            "elements": [{"type": "node", "id": 3, "lat": 48.0, "lon": 2.0, "tags": {"name": "Y"}}],
        })

    with patch("etl.osm.httpx.AsyncClient", _client_factory(handler)):
        adapter = await OverpassAdapter.fetch(
            ["https://a.test/api/interpreter", "https://b.test/api/interpreter"],
            timeout=5.0,
        )
    assert adapter.total_elements == 1


async def test_fetch_raises_when_all_endpoints_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"remark": "runtime error", "elements": []})

    with patch("etl.osm.httpx.AsyncClient", _client_factory(handler)):
        try:
            await OverpassAdapter.fetch(["https://a.test/api/interpreter"], timeout=5.0)
            raise AssertionError("devrait lever RuntimeError")
        except RuntimeError as e:
            assert "résultats partiels" in str(e)


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
