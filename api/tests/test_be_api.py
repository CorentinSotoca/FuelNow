from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import bindparam, text

from app.db import async_session
from app.main import app

BE_TEST_DATE = date(2026, 8, 28)
BE_TEST_DATE_2 = date(2026, 8, 27)

BE_TEST_PRICES = [
    ("gazole", "Diesel B7 (€/L)", 1.732, BE_TEST_DATE),
    ("sp95", "Essence 95 RON E5 (€/L)", 1.789, BE_TEST_DATE),
    ("sp98", "Essence 98 RON E5 (€/L)", 1.849, BE_TEST_DATE),
    ("e10", "Essence 95 RON E10 (€/L)", 1.759, BE_TEST_DATE),
    ("gplc", "Autogas LPG (à la pompe) (€/L)", 0.852, BE_TEST_DATE),
    ("gazole", "Diesel B7 (€/L)", 1.700, BE_TEST_DATE_2),
]


@pytest.fixture()
async def seeded_be_prices():
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        for fuel_code, product_label, price_eur, price_date in BE_TEST_PRICES:
            await session.execute(
                text(
                    "INSERT INTO be_max_prices (fuel_code, product_label, price_eur, price_date, fetched_at) "
                    "VALUES (:fuel_code, :product_label, :price_eur, :price_date, :fetched_at) "
                    "ON CONFLICT (fuel_code, price_date) DO UPDATE SET price_eur = EXCLUDED.price_eur"
                ),
                {
                    "fuel_code": fuel_code,
                    "product_label": product_label,
                    "price_eur": price_eur,
                    "price_date": price_date,
                    "fetched_at": now,
                },
            )
        await session.commit()

    yield

    async with async_session() as session:
        await session.execute(
            text("DELETE FROM be_max_prices WHERE price_date IN :dates").bindparams(
                bindparam("dates", expanding=True)
            ),
            {"dates": [BE_TEST_DATE, BE_TEST_DATE_2]},
        )
        await session.commit()


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_be_prices_all(client, seeded_be_prices):
    resp = await client.get("/api/be/prices")
    assert resp.status_code == 200
    data = resp.json()
    fuel_codes = [p["fuel_code"] for p in data["prices"]]
    assert fuel_codes == ["e10", "gazole", "gplc", "sp95", "sp98"]
    assert data["fetched_at"] is not None


async def test_be_prices_filter_by_fuel(client, seeded_be_prices):
    resp = await client.get("/api/be/prices", params={"fuel": "gazole"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["prices"]) == 1
    assert data["prices"][0]["fuel_code"] == "gazole"
    assert data["prices"][0]["price_eur"] == pytest.approx(1.732)


async def test_be_prices_only_latest_date(client, seeded_be_prices):
    resp = await client.get("/api/be/prices")
    data = resp.json()
    for p in data["prices"]:
        assert p["price_date"] == "2026-08-28"


async def test_be_prices_empty(client):
    resp = await client.get("/api/be/prices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prices"] == []
    assert data["fetched_at"] is None


async def test_be_prices_filter_nonexistent_fuel(client, seeded_be_prices):
    resp = await client.get("/api/be/prices", params={"fuel": "e85"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["prices"] == []
