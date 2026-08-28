from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import bindparam, text

from app.db import async_session
from etl.load import check_guardrail, get_last_run_stats, load_stations_atomically
from etl.models import Fuel, Outage, StationPriceRecord, StationRecord

LOAD_STATION_IDS = [900000100, 900000101, 900000102]


class _Rollback(Exception):
    """Sentinel exception to force transaction rollback in load tests."""


# ---------------------------------------------------------------------------
# check_guardrail
# ---------------------------------------------------------------------------


async def test_check_guardrail_first_run_accepts_at_min():
    with patch("etl.load.get_last_run_stats", new_callable=AsyncMock, return_value=None):
        async with async_session() as session:
            assert await check_guardrail(session, new_count=5000, min_rows=5000, min_ratio=0.8) is True


async def test_check_guardrail_first_run_rejects_below_min():
    with patch("etl.load.get_last_run_stats", new_callable=AsyncMock, return_value=None):
        async with async_session() as session:
            assert await check_guardrail(session, new_count=4999, min_rows=5000, min_ratio=0.8) is False


async def test_check_guardrail_ratio_accept():
    with patch("etl.load.get_last_run_stats", new_callable=AsyncMock, return_value=10000):
        async with async_session() as session:
            assert await check_guardrail(session, new_count=9000, min_rows=5000, min_ratio=0.8) is True


async def test_check_guardrail_ratio_reject():
    with patch("etl.load.get_last_run_stats", new_callable=AsyncMock, return_value=10000):
        async with async_session() as session:
            assert await check_guardrail(session, new_count=7000, min_rows=5000, min_ratio=0.8) is False


async def test_check_guardrail_min_rows_reject():
    with patch("etl.load.get_last_run_stats", new_callable=AsyncMock, return_value=10000):
        async with async_session() as session:
            assert await check_guardrail(session, new_count=4000, min_rows=5000, min_ratio=0.8) is False


# ---------------------------------------------------------------------------
# get_last_run_stats — filtre par source='fr' (fix C4)
# ---------------------------------------------------------------------------


async def test_get_last_run_stats_filters_by_source_fr():
    ts_be = datetime(2099, 1, 2, tzinfo=timezone.utc)
    ts_fr = datetime(2099, 1, 1, tzinfo=timezone.utc)
    inserted_ids: list[int] = []

    async with async_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO etl_runs (started_at, finished_at, status, rows_stations, source) "
                "VALUES (:started, :finished, 'success', 99999, 'be') RETURNING id"
            ),
            {"started": ts_be, "finished": ts_be},
        )
        inserted_ids.append(result.scalar_one())

        result = await session.execute(
            text(
                "INSERT INTO etl_runs (started_at, finished_at, status, rows_stations, source) "
                "VALUES (:started, :finished, 'success', 10000, 'fr') RETURNING id"
            ),
            {"started": ts_fr, "finished": ts_fr},
        )
        inserted_ids.append(result.scalar_one())
        await session.commit()

    try:
        async with async_session() as session:
            result = await get_last_run_stats(session)
            assert result == 10000
    finally:
        async with async_session() as session:
            await session.execute(
                text("DELETE FROM etl_runs WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": inserted_ids},
            )
            await session.commit()


# ---------------------------------------------------------------------------
# load_stations_atomically — TRUNCATE + INSERT atomique
# ---------------------------------------------------------------------------


async def test_load_stations_atomically_replaces_data():
    # Seed old stations that should be replaced by the TRUNCATE
    async with async_session() as session:
        for sid in (900000100, 900000101):
            await session.execute(
                text(
                    "INSERT INTO stations (id, address, city, postal_code, road_type, geom) "
                    "VALUES (:id, 'Old', 'Old', '00000', 'R', "
                    "ST_MakePoint(0.001, 0.001)::geography) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": sid},
            )
        await session.execute(
            text(
                "INSERT INTO station_prices (station_id, fuel, price_eur, price_maj, outage) "
                "VALUES (900000100, 'gazole', 1.500, now(), 'none') "
                "ON CONFLICT (station_id, fuel) DO NOTHING"
            ),
        )
        await session.commit()

    try:
        new_stations = [
            StationRecord(
                id=900000102,
                address="New Station",
                postal_code="00000",
                city="Test",
                road_type="R",
                lon=0.002,
                lat=0.002,
                prices=[
                    StationPriceRecord(
                        fuel=Fuel.gazole,
                        price_eur=1.200,
                        price_maj=datetime.now(timezone.utc),
                        outage=Outage.none,
                    ),
                ],
            ),
        ]

        async with async_session() as session:
            try:
                async with session.begin():
                    rows_st, rows_pr = await load_stations_atomically(session, new_stations)

                    # Old stations replaced, new one present
                    result = await session.execute(text("SELECT id FROM stations ORDER BY id"))
                    station_ids = [r[0] for r in result.fetchall()]
                    assert 900000102 in station_ids
                    assert 900000100 not in station_ids
                    assert 900000101 not in station_ids

                    # Price correctly loaded
                    result = await session.execute(
                        text(
                            "SELECT price_eur FROM station_prices "
                            "WHERE station_id = 900000102 AND fuel = 'gazole'"
                        )
                    )
                    price = result.scalar_one()
                    assert float(price) == pytest.approx(1.200)

                    assert rows_st == 1
                    assert rows_pr == 1

                    # Force rollback to preserve real data
                    raise _Rollback
            except _Rollback:
                pass
    finally:
        async with async_session() as session:
            await session.execute(
                text("DELETE FROM station_prices WHERE station_id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": LOAD_STATION_IDS},
            )
            await session.execute(
                text("DELETE FROM stations WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": LOAD_STATION_IDS},
            )
            await session.commit()
