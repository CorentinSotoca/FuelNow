import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.limiter import limiter
from app.models import FUEL_TYPES
from app.schemas import StationDetailResponse, StationPriceDetail, StationSearchItem, StationSearchResponse
from app.status import get_last_success

router = APIRouter()


_COUNT_SQL = """
    WITH filtered AS (
        SELECT sp.price_eur
        FROM stations s
        LEFT JOIN station_prices sp ON sp.station_id = s.id AND sp.fuel = :fuel
        WHERE ST_DWithin(s.geom, ST_MakePoint(:lon, :lat)::geography, :radius_m)
          AND (:include_unpriced OR sp.price_eur IS NOT NULL)
          AND (:include_outage OR COALESCE(sp.outage, 'none') = 'none')
    )
    SELECT count(*) AS total, min(price_eur) AS min_price FROM filtered
"""

_SEARCH_SQL_TEMPLATE = """
    WITH filtered AS (
        SELECT
            s.id,
            s.address,
            s.city,
            s.postal_code,
            s.road_type,
            ST_Y(s.geom::geometry) AS lat,
            ST_X(s.geom::geometry) AS lon,
            ST_Distance(s.geom, ST_MakePoint(:lon, :lat)::geography) AS distance_m,
            sp.price_eur,
            sp.price_maj,
            COALESCE(sp.outage, 'none') AS outage
        FROM stations s
        LEFT JOIN station_prices sp ON sp.station_id = s.id AND sp.fuel = :fuel
        WHERE ST_DWithin(s.geom, ST_MakePoint(:lon, :lat)::geography, :radius_m)
          AND (:include_unpriced OR sp.price_eur IS NOT NULL)
          AND (:include_outage OR COALESCE(sp.outage, 'none') = 'none')
    )
    SELECT filtered.*
    FROM filtered
    ORDER BY {order_by}
    LIMIT :limit OFFSET :offset
"""

_ORDER_BY_PRICE = "price_eur ASC NULLS LAST, distance_m ASC"
_ORDER_BY_DISTANCE = "distance_m ASC, price_eur ASC NULLS LAST"


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
    offset = (page - 1) * page_size
    order_by = _ORDER_BY_DISTANCE if sort == "distance" else _ORDER_BY_PRICE
    search_sql = text(_SEARCH_SQL_TEMPLATE.format(order_by=order_by))

    count_result = await session.execute(
        text(_COUNT_SQL),
        {
            "lat": lat,
            "lon": lon,
            "radius_m": radius_m,
            "fuel": fuel,
            "include_unpriced": include_unpriced,
            "include_outage": include_outage,
        },
    )
    count_row = count_result.mappings().first()
    total = count_row["total"] if count_row else 0
    min_price = count_row["min_price"] if count_row else None

    result = await session.execute(
        search_sql,
        {
            "lat": lat,
            "lon": lon,
            "radius_m": radius_m,
            "fuel": fuel,
            "include_unpriced": include_unpriced,
            "include_outage": include_outage,
            "limit": page_size,
            "offset": offset,
        },
    )
    rows = result.mappings().all()

    items = [
        StationSearchItem(
            id=r["id"],
            address=r["address"],
            city=r["city"],
            postal_code=r["postal_code"],
            road_type=r["road_type"],
            lat=r["lat"],
            lon=r["lon"],
            distance_m=r["distance_m"],
            price_eur=float(r["price_eur"]) if r["price_eur"] is not None else None,
            price_updated_at=r["price_maj"],
            outage=r["outage"],
            cheapest_delta_eur=(
                float(r["price_eur"]) - float(min_price)
                if r["price_eur"] is not None and min_price is not None
                else None
            ),
        )
        for r in rows
    ]

    data_updated_at, stale = await get_last_success(session)

    etag_input = f"{lat}:{lon}:{radius_m}:{fuel}:{include_unpriced}:{include_outage}:{sort}:{page}:{page_size}:{data_updated_at}:{total}"
    etag = hashlib.md5(etag_input.encode()).hexdigest()
    cache_control = f"public, max-age={settings.cache_ttl_s}"

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})

    body = StationSearchResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        data_updated_at=data_updated_at,
        stale=stale,
    )

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control
    return body


@router.get("/api/stations/{station_id}", response_model=StationDetailResponse)
@limiter.limit(f"{settings.rate_limit_per_min}/minute")
async def get_station(
    request: Request,
    station_id: int,
    session: AsyncSession = Depends(get_session),
) -> StationDetailResponse:
    result = await session.execute(
        text(
            """
            SELECT id, address, city, postal_code, dept_code, dept_name, region_name, road_type,
                   ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lon, services, opening_hours
            FROM stations WHERE id = :id
            """
        ),
        {"id": station_id},
    )
    station = result.mappings().first()
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")

    prices_result = await session.execute(
        text("SELECT fuel, price_eur, price_maj, outage FROM station_prices WHERE station_id = :id"),
        {"id": station_id},
    )
    prices = [
        StationPriceDetail(
            fuel=p["fuel"],
            price_eur=float(p["price_eur"]) if p["price_eur"] is not None else None,
            price_maj=p["price_maj"],
            outage=p["outage"],
        )
        for p in prices_result.mappings().all()
    ]

    return StationDetailResponse(
        id=station["id"],
        address=station["address"],
        city=station["city"],
        postal_code=station["postal_code"],
        dept_code=station["dept_code"],
        dept_name=station["dept_name"],
        region_name=station["region_name"],
        road_type=station["road_type"],
        lat=station["lat"],
        lon=station["lon"],
        services=station["services"],
        opening_hours=station["opening_hours"],
        prices=prices,
    )
