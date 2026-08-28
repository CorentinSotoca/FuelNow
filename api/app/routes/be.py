from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.limiter import limiter
from app.schemas import BeMaxPriceItem, BeMaxPriceResponse

router = APIRouter()


@router.get("/api/be/prices", response_model=BeMaxPriceResponse)
@limiter.limit(f"{settings.rate_limit_per_min}/minute")
async def get_be_prices(
    request: Request,
    fuel: str | None = Query(None, pattern="^(gazole|sp95|sp98|e10|e85|gplc)$"),
    session: AsyncSession = Depends(get_session),
) -> BeMaxPriceResponse:
    if fuel is not None:
        result = await session.execute(
            text(
                "SELECT fuel_code, product_label, price_eur, price_date, fetched_at "
                "FROM be_max_prices "
                "WHERE price_date = (SELECT MAX(price_date) FROM be_max_prices) "
                "AND fuel_code = :fuel "
                "ORDER BY fuel_code"
            ),
            {"fuel": fuel},
        )
    else:
        result = await session.execute(
            text(
                "SELECT fuel_code, product_label, price_eur, price_date, fetched_at "
                "FROM be_max_prices "
                "WHERE price_date = (SELECT MAX(price_date) FROM be_max_prices) "
                "ORDER BY fuel_code"
            )
        )
    rows = result.mappings().all()

    fetched_at = rows[0]["fetched_at"] if rows else None
    prices = [
        BeMaxPriceItem(
            fuel_code=r["fuel_code"],
            product_label=r["product_label"],
            price_eur=float(r["price_eur"]),
            price_date=r["price_date"],
        )
        for r in rows
    ]

    return BeMaxPriceResponse(prices=prices, fetched_at=fetched_at)
