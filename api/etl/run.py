from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import structlog
from sqlalchemy import text

from app.config import settings
from app.db import async_session
from etl.adapters import OdsJsonAdapter
from etl.load import check_guardrail, load_stations_atomically, purge_etl_runs
from etl.runs import cleanup_orphaned_runs, create_run, send_alert, update_run

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger("etl")


async def run_etl() -> None:
    started_at = datetime.now(UTC)
    logger.info("etl_started")

    run_id = await create_run(started_at, source="fr")
    await cleanup_orphaned_runs(source="fr")

    try:
        adapter = await OdsJsonAdapter.fetch(
            settings.source_dataset_url,
        )

        stations = list(adapter.iter_stations())
        count = len(stations)
        rejected = adapter.rejected_count
        logger.info("stations_parsed", count=count, rejected=rejected)

        async with async_session() as session:
            ok = await check_guardrail(
                session, count, settings.etl_min_rows, settings.etl_min_ratio
            )
            await session.commit()

        if not ok:
            msg = f"Guardrail failed: {count} stations below threshold"
            logger.error("guardrail_failed", count=count)
            await update_run(run_id, "failed", error=msg, finished_at=datetime.now(UTC))
            await send_alert(msg, label="ETL")
            return

        async with async_session() as session:
            async with session.begin():
                rows_st, rows_pr = await load_stations_atomically(session, stations)
                await session.execute(text("ANALYZE stations"))
                await session.execute(text("ANALYZE station_prices"))
                await purge_etl_runs(session)

            logger.info("load_complete", rows_stations=rows_st, rows_prices=rows_pr)
            await update_run(
                run_id,
                "success",
                rows_stations=rows_st,
                rows_prices=rows_pr,
                finished_at=datetime.now(UTC),
            )

    except Exception as e:
        logger.exception("etl_failed", error=str(e))
        await update_run(run_id, "failed", error=str(e), finished_at=datetime.now(UTC))
        await send_alert(str(e), label="ETL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_etl())
