from __future__ import annotations

import logging
from datetime import UTC, datetime

from geoalchemy2 import Geography
from sqlalchemy import TIMESTAMP, BigInteger, Column, MetaData, Numeric, Table, Text, insert, text
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FUEL_TYPES, OUTAGE_TYPES
from etl.models import StationRecord

logger = logging.getLogger(__name__)

_metadata = MetaData()

_stations_stg = Table(
    "stations_stg", _metadata,
    Column("id", BigInteger, primary_key=True),
    Column("address", Text),
    Column("postal_code", Text),
    Column("city", Text),
    Column("dept_code", Text),
    Column("dept_name", Text),
    Column("region_name", Text),
    Column("road_type", Text),
    Column("geom", Geography("POINT", srid=4326)),
    Column("services", JSONB),
    Column("opening_hours", JSONB),
    Column("updated_at", TIMESTAMP(timezone=True)),
    prefixes=["TEMPORARY"],
)

_prices_stg = Table(
    "station_prices_stg", _metadata,
    Column("station_id", BigInteger),
    Column("fuel", PG_ENUM(*FUEL_TYPES, name="fuel_type", create_type=False)),
    Column("price_eur", Numeric(5, 3)),
    Column("price_maj", TIMESTAMP(timezone=True)),
    Column("outage", PG_ENUM(*OUTAGE_TYPES, name="outage_type", create_type=False)),
    prefixes=["TEMPORARY"],
)


async def get_last_run_stats(session: AsyncSession) -> int | None:
    result = await session.execute(
        text("SELECT rows_stations FROM etl_runs WHERE status='success' AND source='fr' ORDER BY finished_at DESC LIMIT 1")
    )
    row = result.fetchone()
    if row:
        return row[0]
    return None


async def check_guardrail(
    session: AsyncSession,
    new_count: int,
    min_rows: int,
    min_ratio: float,
) -> bool:
    last_count = await get_last_run_stats(session)
    if last_count is None:
        return new_count >= min_rows
    ratio = new_count / last_count if last_count > 0 else 0
    return new_count >= min_rows and ratio >= min_ratio


async def load_stations_atomically(
    session: AsyncSession,
    stations: list[StationRecord],
) -> tuple[int, int]:
    rows_stations = len(stations)
    rows_prices = sum(len(s.prices) for s in stations)

    await session.execute(text(
        "CREATE TEMP TABLE stations_stg (LIKE stations INCLUDING ALL) ON COMMIT DROP"
    ))
    await session.execute(text(
        "CREATE TEMP TABLE station_prices_stg (LIKE station_prices INCLUDING ALL) ON COMMIT DROP"
    ))

    batch_size = 500

    station_rows = []
    for s in stations:
        station_rows.append({
            "id": s.id,
            "address": s.address,
            "postal_code": s.postal_code,
            "city": s.city,
            "dept_code": s.dept_code,
            "dept_name": s.dept_name,
            "region_name": s.region_name,
            "road_type": s.road_type,
            "geom": f"SRID=4326;POINT({s.lon} {s.lat})",
            "services": s.services,
            "opening_hours": s.opening_hours,
            "updated_at": datetime.now(UTC),
        })

    for i in range(0, len(station_rows), batch_size):
        await session.execute(insert(_stations_stg), station_rows[i : i + batch_size])

    price_rows = []
    for s in stations:
        for p in s.prices:
            price_rows.append({
                "station_id": s.id,
                "fuel": p.fuel.value,
                "price_eur": p.price_eur,
                "price_maj": p.price_maj,
                "outage": p.outage.value,
            })

    for i in range(0, len(price_rows), batch_size):
        await session.execute(insert(_prices_stg), price_rows[i : i + batch_size])

    await session.execute(text("TRUNCATE station_prices, stations"))
    await session.execute(text("INSERT INTO stations SELECT * FROM stations_stg"))
    await session.execute(text("INSERT INTO station_prices SELECT * FROM station_prices_stg"))

    return rows_stations, rows_prices


async def purge_etl_runs(session: AsyncSession, days: int = 30) -> None:
    await session.execute(
        text("DELETE FROM etl_runs WHERE started_at < now() - make_interval(days => :days)").bindparams(days=days)
    )
