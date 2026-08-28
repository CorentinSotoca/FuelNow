from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import HealthResponse
from app.status import get_last_success

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    last_success_at, stale = await get_last_success(session)
    age_hours = None
    if last_success_at is not None:
        age_hours = (datetime.now(timezone.utc) - last_success_at).total_seconds() / 3600
    return HealthResponse(
        status="ok",
        last_success_at=last_success_at,
        age_hours=age_hours,
        stale=stale,
    )
