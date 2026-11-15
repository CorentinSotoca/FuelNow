from typing import Literal

from mcp.server.mcpserver import MCPServer

from app.db import async_session
from app import services

mcp = MCPServer("FuelNow")


@mcp.tool()
async def search_stations(
    lat: float,
    lon: float,
    fuel: Literal["gazole", "sp95", "sp98", "e10", "e85", "gplc", "sp95-e10"] = "gazole",
    radius_m: int = 5000,
    sort: Literal["price", "distance"] = "price",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Find the cheapest fuel stations near a geographic point in France.

    Returns stations sorted by fuel price or distance, with price, brand,
    address, and distance from the search point.

    Args:
        lat: Latitude (e.g. 48.8566 for Paris)
        lon: Longitude (e.g. 2.3522 for Paris)
        fuel: Fuel type — one of: gazole, sp95, sp98, e10, e85, gplc, or
              sp95-e10 (SP95 and SP95-E10 merged: cheapest of the two per station)
        radius_m: Search radius in meters (500–30000, default 5000)
        sort: Sort order — "price" (cheapest first) or "distance" (nearest first)
        page: Page number (1-based)
        page_size: Results per page (1–100, default 25)

    Returns:
        Dict with items (list of stations), total, page, page_size,
        min_price_eur (cheapest price in the radius), data_updated_at,
        and stale flag.
    """
    async with async_session() as session:
        return await services.search_stations(
            session,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            fuel=fuel,
            sort=sort,
            page=page,
            page_size=page_size,
        )


@mcp.tool()
async def get_station_detail(station_id: int) -> dict:
    """Get detailed information about a specific fuel station.

    Returns address, coordinates, services, opening hours, and all fuel prices.

    Args:
        station_id: The station ID (from search_stations results)
    """
    async with async_session() as session:
        return await services.get_station_detail(session, station_id)


@mcp.tool()
async def list_fuels() -> list[dict]:
    """List the selectable fuel types.

    Returns 5 fuel codes and their labels: gazole, sp95-e10 (SP95 and E10
    merged — cheapest of the two per station), sp98, e85, gplc.
    """
    return services.list_fuels()


@mcp.tool()
async def get_be_prices(
    fuel: Literal["gazole", "sp95", "sp98", "e10", "e85", "gplc"] | None = None,
) -> dict:
    """Get maximum regulated fuel prices in Belgium.

    Returns the official maximum prices set by the Belgian government.

    Args:
        fuel: Optional fuel type filter — one of: gazole, sp95, sp98, e10, e85, gplc.
              If omitted, returns all fuel types.
    """
    async with async_session() as session:
        return await services.get_be_prices(session, fuel)


@mcp.tool()
async def get_health() -> dict:
    """Check FuelNow API health and data freshness.

    Returns the status, last successful ETL run time, age in hours, and
    whether the data is stale (older than 26 hours).
    """
    async with async_session() as session:
        return await services.get_health_status(session)
