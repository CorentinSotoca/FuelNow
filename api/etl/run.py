from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session
from etl.adapters import OdsJsonAdapter
from etl.load import check_guardrail, load_stations_atomically, purge_etl_runs

logging.basicConfig(
    level=logging.getLevelName(settings.log_level),
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("etl")


async def run_etl() -> None:
    started_at = datetime.now(timezone.utc)
    logger.info("ETL started")

    run_id = await _create_run(started_at)

    try:
        adapter, etag = await OdsJsonAdapter.fetch(
            settings.source_dataset_url,
        )

        if adapter is None:
            logger.info("Source not modified (304), skipping")
            await _update_run(run_id, "skipped", finished_at=datetime.now(timezone.utc))
            return

        stations = list(adapter.iter_stations())
        count = len(stations)
        rejected = adapter.rejected_count
        logger.info(f"Parsed {count} stations ({rejected} rejected)")

        async with async_session() as session:
            ok = await check_guardrail(
                session, count, settings.etl_min_rows, settings.etl_min_ratio
            )
            await session.commit()

        if not ok:
            msg = f"Guardrail failed: {count} stations below threshold"
            logger.error(msg)
            await _update_run(run_id, "failed", error=msg, finished_at=datetime.now(timezone.utc))
            await _send_alert(msg)
            return

        async with async_session() as session:
            async with session.begin():
                rows_st, rows_pr = await load_stations_atomically(session, stations)
                await session.execute(text("ANALYZE stations"))
                await session.execute(text("ANALYZE station_prices"))
                await purge_etl_runs(session)

            logger.info(f"Loaded {rows_st} stations, {rows_pr} prices")
            await _update_run(
                run_id,
                "success",
                rows_stations=rows_st,
                rows_prices=rows_pr,
                finished_at=datetime.now(timezone.utc),
            )

    except Exception as e:
        logger.exception("ETL failed")
        await _update_run(run_id, "failed", error=str(e), finished_at=datetime.now(timezone.utc))
        await _send_alert(str(e))
        sys.exit(1)


async def _create_run(started_at: datetime) -> int:
    async with async_session() as session:
        result = await session.execute(
            text("INSERT INTO etl_runs (started_at, status) VALUES (:ts, 'running') RETURNING id"),
            {"ts": started_at},
        )
        run_id = result.scalar_one()
        await session.commit()
        return run_id


async def _update_run(
    run_id: int,
    status: str,
    *,
    rows_stations: int | None = None,
    rows_prices: int | None = None,
    error: str | None = None,
    finished_at: datetime | None = None,
) -> None:
    async with async_session() as session:
        await session.execute(
            text(
                "UPDATE etl_runs SET status=:status, rows_stations=:rs, rows_prices=:rp, "
                "error=:err, finished_at=:ft WHERE id=:id"
            ),
            {
                "status": status,
                "rs": rows_stations,
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
            await client.post(settings.alert_webhook_url, json={"text": f"FuelNow ETL: {msg}"})
    except Exception:
        logger.warning("Failed to send alert", exc_info=True)


if __name__ == "__main__":
    asyncio.run(run_etl())
