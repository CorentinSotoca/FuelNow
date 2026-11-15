from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import FUEL_LABELS
from app.status import get_last_success

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
            COALESCE(sp.outage, 'none') AS outage,
            sb.brand,
            sb.osm_name
        FROM stations s
        LEFT JOIN station_prices sp ON sp.station_id = s.id AND sp.fuel = :fuel
        LEFT JOIN station_brands sb ON sb.station_id = s.id
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


async def search_stations(
    session: AsyncSession,
    lat: float,
    lon: float,
    radius_m: int = 5000,
    fuel: str = "gazole",
    include_unpriced: bool = False,
    include_outage: bool = False,
    sort: str = "price",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
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
        {
            "id": r["id"],
            "address": r["address"],
            "city": r["city"],
            "postal_code": r["postal_code"],
            "road_type": r["road_type"],
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "distance_m": float(r["distance_m"]),
            "price_eur": float(r["price_eur"]) if r["price_eur"] is not None else None,
            "price_updated_at": r["price_maj"],
            "outage": r["outage"],
            "brand": r["brand"],
            "osm_name": r["osm_name"],
            "cheapest_delta_eur": (
                float(r["price_eur"]) - float(min_price)
                if r["price_eur"] is not None and min_price is not None
                else None
            ),
        }
        for r in rows
    ]

    data_updated_at, stale = await get_last_success(session)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "data_updated_at": data_updated_at,
        "stale": stale,
    }


async def get_station_detail(session: AsyncSession, station_id: int) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            SELECT s.id, s.address, s.city, s.postal_code, s.dept_code, s.dept_name, s.region_name, s.road_type,
                   ST_Y(s.geom::geometry) AS lat, ST_X(s.geom::geometry) AS lon, s.services, s.opening_hours,
                   sb.brand, sb.osm_name
            FROM stations s
            LEFT JOIN station_brands sb ON sb.station_id = s.id
            WHERE s.id = :id
            """
        ),
        {"id": station_id},
    )
    station = result.mappings().first()
    if station is None:
        return None

    prices_result = await session.execute(
        text("SELECT fuel, price_eur, price_maj, outage FROM station_prices WHERE station_id = :id"),
        {"id": station_id},
    )
    prices = [
        {
            "fuel": p["fuel"],
            "price_eur": float(p["price_eur"]) if p["price_eur"] is not None else None,
            "price_maj": p["price_maj"],
            "outage": p["outage"],
        }
        for p in prices_result.mappings().all()
    ]

    return {
        "id": station["id"],
        "address": station["address"],
        "city": station["city"],
        "postal_code": station["postal_code"],
        "dept_code": station["dept_code"],
        "dept_name": station["dept_name"],
        "region_name": station["region_name"],
        "road_type": station["road_type"],
        "lat": float(station["lat"]),
        "lon": float(station["lon"]),
        "services": station["services"],
        "opening_hours": station["opening_hours"],
        "brand": station["brand"],
        "osm_name": station["osm_name"],
        "prices": prices,
    }


def list_fuels() -> list[dict[str, str]]:
    from app.models import FUEL_TYPES

    return [{"code": f, "label": FUEL_LABELS[f]} for f in FUEL_TYPES]


async def get_be_prices(session: AsyncSession, fuel: str | None = None) -> dict[str, Any]:
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
        {
            "fuel_code": r["fuel_code"],
            "product_label": r["product_label"],
            "price_eur": float(r["price_eur"]),
            "price_date": r["price_date"],
        }
        for r in rows
    ]

    return {"prices": prices, "fetched_at": fetched_at}


async def get_health_status(session: AsyncSession) -> dict[str, Any]:
    last_success_at, stale = await get_last_success(session)
    age_hours = None
    if last_success_at is not None:
        age_hours = (datetime.now(UTC) - last_success_at).total_seconds() / 3600
    return {
        "status": "ok",
        "last_success_at": last_success_at,
        "age_hours": age_hours,
        "stale": stale,
    }
