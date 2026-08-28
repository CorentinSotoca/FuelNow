from __future__ import annotations

from datetime import datetime

import structlog
from sqlalchemy import text

from app.config import settings
from app.db import async_session

logger = structlog.get_logger("etl.runs")


async def create_run(started_at: datetime, source: str) -> int:
    async with async_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO etl_runs (started_at, status, source) "
                "VALUES (:ts, 'running', :source) RETURNING id"
            ),
            {"ts": started_at, "source": source},
        )
        run_id = result.scalar_one()
        await session.commit()
        return run_id


async def update_run(
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


async def send_alert(msg: str, *, label: str = "ETL") -> None:
    if not settings.alert_webhook_url:
        return
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                settings.alert_webhook_url,
                json={"text": f"FuelNow {label}: {msg}"},
            )
    except Exception:
        logger.warning("alert_send_failed", exc_info=True)


async def cleanup_orphaned_runs(source: str) -> None:
    async with async_session() as session:
        await session.execute(
            text(
                "UPDATE etl_runs SET status='failed', error='orphaned run (crashed)', finished_at=now() "
                "WHERE status='running' AND source=:source "
                "AND started_at < now() - interval '2 hours'"
            ),
            {"source": source},
        )
        await session.commit()
