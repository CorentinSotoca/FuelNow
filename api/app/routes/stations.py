import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.limiter import limiter
from app.models import FUEL_TYPES
from app.schemas import StationDetailResponse, StationPriceDetail, StationSearchItem, StationSearchResponse
from app import services

router = APIRouter()


@router.get("/api/stations/search", response_model=StationSearchResponse)
@limiter.limit(f"{settings.rate_limit_per_min}/minute")
async def search_stations(
    request: Request,
    response: Response,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(5000, ge=500, le=settings.search_radius_max_m),
    fuel: str = Query(..., pattern="^(" + "|".join(FUEL_TYPES) + ")$"),
    include_unpriced: bool = Query(False),
    include_outage: bool = Query(False),
    sort: Literal["price", "distance"] = Query("price"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> StationSearchResponse:
    data = await services.search_stations(
        session,
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        fuel=fuel,
        include_unpriced=include_unpriced,
        include_outage=include_outage,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    etag_input = f"{lat}:{lon}:{radius_m}:{fuel}:{include_unpriced}:{include_outage}:{sort}:{page}:{page_size}:{data['data_updated_at']}:{data['total']}"
    etag = hashlib.md5(etag_input.encode()).hexdigest()
    cache_control = f"public, max-age={settings.cache_ttl_s}"

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})

    items = [StationSearchItem(**item) for item in data["items"]]

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control
    return StationSearchResponse(
        items=items,
        total=data["total"],
        page=data["page"],
        page_size=data["page_size"],
        data_updated_at=data["data_updated_at"],
        stale=data["stale"],
    )


@router.get("/api/stations/{station_id}", response_model=StationDetailResponse)
@limiter.limit(f"{settings.rate_limit_per_min}/minute")
async def get_station(
    request: Request,
    station_id: int,
    session: AsyncSession = Depends(get_session),
) -> StationDetailResponse:
    data = await services.get_station_detail(session, station_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Station not found")

    prices = [StationPriceDetail(**p) for p in data["prices"]]
    return StationDetailResponse(
        id=data["id"],
        address=data["address"],
        city=data["city"],
        postal_code=data["postal_code"],
        dept_code=data["dept_code"],
        dept_name=data["dept_name"],
        region_name=data["region_name"],
        road_type=data["road_type"],
        lat=data["lat"],
        lon=data["lon"],
        services=data["services"],
        opening_hours=data["opening_hours"],
        brand=data["brand"],
        osm_name=data["osm_name"],
        prices=prices,
    )
