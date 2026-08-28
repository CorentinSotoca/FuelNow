from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session


@pytest.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
        if session.in_transaction():
            await session.rollback()


async def cleanup_stations(station_ids: list[int]) -> None:
    async with async_session() as session:
        await session.execute(
            text("DELETE FROM station_prices WHERE station_id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": station_ids},
        )
        await session.execute(
            text("DELETE FROM stations WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": station_ids},
        )
        await session.commit()


async def cleanup_etl_runs(run_ids: list[int]) -> None:
    async with async_session() as session:
        await session.execute(
            text("DELETE FROM etl_runs WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": run_ids},
        )
        await session.commit()
