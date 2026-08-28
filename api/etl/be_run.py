from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session
from etl.be_adapter import StatbelAdapter

logging.basicConfig(
    level=logging.getLevelName(settings.log_level),
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("etl.be")


async def run_be_etl() -> None:
    started_at = datetime.now(timezone.utc)
    logger.info("BE ETL started")

    run_id = await _create_run(started_at)

    try:
        adapter = await StatbelAdapter.fetch(settings.statbel_api_url)
        records = adapter.parse()
        count = len(records)
        logger.info(f"Parsed {count} BE max price records")

        if count == 0:
            msg = "No BE max price records parsed"
            logger.error(msg)
            await _update_run(run_id, "failed", error=msg, finished_at=datetime.now(timezone.utc))
            await _send_alert(msg)
            return

        async with async_session() as session:
            async with session.begin():
                rows_inserted = await _upsert_prices(session, records)
            logger.info(f"Upserted {rows_inserted} BE max price rows")
            await _update_run(
                run_id,
                "success",
                rows_prices=rows_inserted,
                finished_at=datetime.now(timezone.utc),
            )

    except Exception as e:
        logger.exception("BE ETL failed")
        await _update_run(run_id, "failed", error=str(e), finished_at=datetime.now(timezone.utc))
        await _send_alert(str(e))
        sys.exit(1)


async def _upsert_prices(session: AsyncSession, records: list) -> int:
    from datetime import datetime, timezone
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


async def _create_run(started_at: datetime) -> int:
    async with async_session() as session:
        result = await session.execute(
            text("INSERT INTO etl_runs (started_at, status, source) VALUES (:ts, 'running', 'be') RETURNING id"),
            {"ts": started_at},
        )
        run_id = result.scalar_one()
        await session.commit()
        return run_id


async def _update_run(
    run_id: int,
    status: str,
    *,
    rows_prices: int | None = None,
    error: str | None = None,
    finished_at: datetime | None = None,
) -> None:
    async with async_session() as session:
        await session.execute(
            text(
                "UPDATE etl_runs SET status=:status, rows_prices=:rp, "
                "error=:err, finished_at=:ft WHERE id=:id"
            ),
            {
                "status": status,
                "rp": rows_prices,
                "err": error,
                "ft": finished_at,
                "id": run_id,
            },
        )
        await session.commit()


async def _send_alert(msg: str) -> None:
    if not settings.alert_webhook_url:
        return
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.alert_webhook_url, json={"text": f"FuelNow BE ETL: {msg}"})
    except Exception:
        logger.warning("Failed to send alert", exc_info=True)


if __name__ == "__main__":
    asyncio.run(run_be_etl())
