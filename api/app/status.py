from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

STALE_THRESHOLD_HOURS = 26


async def get_last_success(session: AsyncSession) -> tuple[datetime | None, bool]:
    result = await session.execute(
        text("SELECT finished_at FROM etl_runs WHERE status='success' ORDER BY finished_at DESC LIMIT 1")
    )
    row = result.fetchone()
    if not row or row[0] is None:
        return None, True
    finished_at = row[0]
    age_hours = (datetime.now(timezone.utc) - finished_at).total_seconds() / 3600
    stale = age_hours > STALE_THRESHOLD_HOURS
    return finished_at, stale
