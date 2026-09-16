from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import bindparam, text

from app.db import async_session
from app.main import app

# Sentinel test stations placed in the middle of the Gulf of Guinea (0,0),
# far from any real French station, to avoid interfering with production data
# already loaded by the ETL.
TEST_STATION_IDS = [900000001, 900000002, 900000003, 900000004, 900000005]

STATIONS = [
    # id, lat, lon
    (900000001, 0.001, 0.001),
    (900000002, 0.002, 0.001),
    (900000003, 0.0005, 0.0005),
    (900000004, 0.001, 0.002),  # no price row for gazole
    (900000005, 0.0015, 0.0015),  # outage=temporary
]

# station_id, fuel, price_eur, outage
PRICES = [
    (900000001, "gazole", 1.500, "none"),
    (900000002, "gazole", 1.200, "none"),
    (900000003, "gazole", 1.200, "none"),
    (900000005, "gazole", 1.100, "temporary"),
]


@pytest.fixture()
async def seeded_db():
    async with async_session() as session:
        for sid, lat, lon in STATIONS:
            await session.execute(
                text(
                    "INSERT INTO stations (id, address, city, postal_code, road_type, geom) "
                    "VALUES (:id, 'Test', 'Test', '00000', 'R', ST_MakePoint(:lon, :lat)::geography) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": sid, "lat": lat, "lon": lon},
            )
        for sid, fuel, price, outage in PRICES:
            await session.execute(
                text(
                    "INSERT INTO station_prices (station_id, fuel, price_eur, price_maj, outage) "
                    "VALUES (:sid, :fuel, :price, now(), :outage) "
                    "ON CONFLICT (station_id, fuel) DO NOTHING"
                ),
                {"sid": sid, "fuel": fuel, "price": price, "outage": outage},
            )
        await session.commit()

    yield

    async with async_session() as session:
        await session.execute(
            text("DELETE FROM station_prices WHERE station_id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": TEST_STATION_IDS},
        )
        await session.execute(
            text("DELETE FROM stations WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": TEST_STATION_IDS},
        )
        await session.commit()


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_search_default_excludes_unpriced_and_outage(client, seeded_db):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "gazole"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [i["id"] for i in data["items"]]
    assert ids == [900000003, 900000002, 900000001]
    assert data["total"] == 3


async def test_search_sort_distance(client, seeded_db):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "gazole", "sort": "distance"},
    )
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["items"]]
    assert ids == [900000003, 900000001, 900000002]


async def test_search_include_unpriced(client, seeded_db):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "gazole", "include_unpriced": True},
    )
    data = resp.json()
    ids = [i["id"] for i in data["items"]]
    assert ids == [900000003, 900000002, 900000001, 900000004]
    assert data["items"][-1]["price_eur"] is None


async def test_search_include_outage(client, seeded_db):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "gazole", "include_outage": True},
    )
    data = resp.json()
    ids = [i["id"] for i in data["items"]]
    assert ids == [900000005, 900000003, 900000002, 900000001]


async def test_search_pagination(client, seeded_db):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "gazole", "page_size": 1, "page": 1},
    )
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] == 3
    assert data["items"][0]["id"] == 900000003


async def test_search_invalid_lat_returns_422(client):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 999, "lon": 0.0, "radius_m": 1000, "fuel": "gazole"},
    )
    assert resp.status_code == 422


async def test_search_invalid_fuel_returns_422(client):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "kerosene"},
    )
    assert resp.status_code == 422


async def test_search_invalid_radius_returns_422(client):
    resp = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 100, "fuel": "gazole"},
    )
    assert resp.status_code == 422


async def test_station_detail_found(client, seeded_db):
    resp = await client.get("/api/stations/900000001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 900000001
    assert any(p["fuel"] == "gazole" and p["price_eur"] == 1.5 for p in data["prices"])


async def test_station_detail_not_found(client):
    resp = await client.get("/api/stations/999999999")
    assert resp.status_code == 404


async def test_search_etag_returns_304(client, seeded_db):
    resp1 = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "gazole"},
    )
    etag = resp1.headers["etag"]
    resp2 = await client.get(
        "/api/stations/search",
        params={"lat": 0.0, "lon": 0.0, "radius_m": 1000, "fuel": "gazole"},
        headers={"If-None-Match": etag},
    )
    assert resp2.status_code == 304
