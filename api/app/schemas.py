from datetime import date, datetime, timezone

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    last_success_at: datetime | None
    age_hours: float | None
    stale: bool


class FuelInfo(BaseModel):
    code: str
    label: str


FUEL_LABELS: dict[str, str] = {
    "gazole": "Gazole",
    "sp95": "SP95",
    "sp98": "SP98",
    "e10": "E10",
    "e85": "E85",
    "gplc": "GPLc",
}


class StationSearchItem(BaseModel):
    id: int
    address: str | None
    city: str | None
    postal_code: str | None
    road_type: str | None
    lat: float
    lon: float
    distance_m: float
    price_eur: float | None
    price_updated_at: datetime | None
    outage: str
    cheapest_delta_eur: float | None


class StationSearchResponse(BaseModel):
    items: list[StationSearchItem]
    total: int
    page: int
    page_size: int
    data_updated_at: datetime | None
    stale: bool


class StationPriceDetail(BaseModel):
    fuel: str
    price_eur: float | None
    price_maj: datetime | None
    outage: str


class StationDetailResponse(BaseModel):
    id: int
    address: str | None
    city: str | None
    postal_code: str | None
    dept_code: str | None
    dept_name: str | None
    region_name: str | None
    road_type: str | None
    lat: float
    lon: float
    services: dict | None
    opening_hours: dict | None
    prices: list[StationPriceDetail]


class BeMaxPriceItem(BaseModel):
    fuel_code: str
    product_label: str
    price_eur: float
    price_date: date


class BeMaxPriceResponse(BaseModel):
    prices: list[BeMaxPriceItem]
    fetched_at: datetime | None
