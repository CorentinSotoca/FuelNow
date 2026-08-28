from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session
from etl.be_adapter import StatbelAdapter
from etl.runs import cleanup_orphaned_runs, create_run, send_alert, update_run

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger("etl.be")


async def run_be_etl() -> None:
    started_at = datetime.now(timezone.utc)
    logger.info("be_etl_started")

    run_id = await create_run(started_at, source="be")
    await cleanup_orphaned_runs(source="be")

    try:
        adapter = await StatbelAdapter.fetch(settings.statbel_api_url)
        records = adapter.parse()
        count = len(records)
        logger.info("be_prices_parsed", count=count)

        if count == 0:
            msg = "No BE max price records parsed"
            logger.error("be_parse_empty")
            await update_run(run_id, "failed", error=msg, finished_at=datetime.now(timezone.utc))
            await send_alert(msg, label="BE ETL")
            return

        async with async_session() as session:
            async with session.begin():
                rows_inserted = await _upsert_prices(session, records)
            logger.info("be_upsert_complete", rows_inserted=rows_inserted)
            await update_run(
                run_id,
                "success",
                rows_prices=rows_inserted,
                finished_at=datetime.now(timezone.utc),
            )

    except Exception as e:
        logger.error("be_etl_failed", error=str(e), exc_info=True)
        await update_run(run_id, "failed", error=str(e), finished_at=datetime.now(timezone.utc))
        await send_alert(str(e), label="BE ETL")
        sys.exit(1)


async def _upsert_prices(session: AsyncSession, records: list) -> int:
    now = datetime.now(timezone.utc)
    rows = 0
    for rec in records:
        result = await session.execute(
            text(
                "INSERT INTO be_max_prices (fuel_code, product_label, price_eur, price_date, fetched_at) "
                "VALUES (:fuel_code, :product_label, :price_eur, :price_date, :fetched_at) "
                "ON CONFLICT (fuel_code, price_date) DO UPDATE SET "
                "product_label = EXCLUDED.product_label, "
                "price_eur = EXCLUDED.price_eur, "
                "fetched_at = EXCLUDED.fetched_at"
            ),
            {
                "fuel_code": rec.fuel_code,
                "product_label": rec.product_label,
                "price_eur": rec.price_eur,
                "price_date": rec.price_date,
                "fetched_at": now,
            },
        )
        rows += result.rowcount
    return rows


if __name__ == "__main__":
    asyncio.run(run_be_etl())
