from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.limiter import limiter
from app.schemas import BeMaxPriceItem, BeMaxPriceResponse
from app import services

router = APIRouter()


@router.get("/api/be/prices", response_model=BeMaxPriceResponse)
@limiter.limit(f"{settings.rate_limit_per_min}/minute")
async def get_be_prices(
    request: Request,
    fuel: str | None = Query(None, pattern="^(gazole|sp95|sp98|e10|e85|gplc)$"),
    session: AsyncSession = Depends(get_session),
) -> BeMaxPriceResponse:
    data = await services.get_be_prices(session, fuel)
    prices = [BeMaxPriceItem(**p) for p in data["prices"]]
    return BeMaxPriceResponse(prices=prices, fetched_at=data["fetched_at"])
