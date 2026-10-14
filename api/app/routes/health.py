from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.limiter import limiter
from app.schemas import HealthResponse
from app import services

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
@limiter.limit(f"{settings.rate_limit_per_min}/minute")
async def health(request: Request, session: AsyncSession = Depends(get_session)) -> HealthResponse:
    data = await services.get_health_status(session)
    return HealthResponse(**data)
