from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


class Fuel(str, Enum):
    gazole = "gazole"
    sp95 = "sp95"
    sp98 = "sp98"
    e10 = "e10"
    e85 = "e85"
    gplc = "gplc"


class Outage(str, Enum):
    none = "none"
    temporary = "temporary"
    definitive = "definitive"


FUEL_FIELD_MAP: dict[str, Fuel] = {
    "gazole": Fuel.gazole,
    "sp95": Fuel.sp95,
    "sp98": Fuel.sp98,
    "e10": Fuel.e10,
    "e85": Fuel.e85,
    "gplc": Fuel.gplc,
}

PRICE_MIN = 0.5
PRICE_MAX = 5.0

FRANCE_BBOX = (-180.0, -90.0, 180.0, 90.0)


class StationPriceRecord(BaseModel):
    fuel: Fuel
    price_eur: float | None = None
    price_maj: datetime | None = None
    outage: Outage = Outage.none


class StationRecord(BaseModel):
    id: int
    address: str | None = None
    postal_code: str | None = None
    city: str | None = None
    dept_code: str | None = None
    dept_name: str | None = None
    region_name: str | None = None
    road_type: str | None = None
    lon: float
    lat: float
    services: dict[str, Any] | None = None
    opening_hours: dict[str, Any] | None = None
    prices: list[StationPriceRecord] = []

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError(f"lat hors bornes: {v}")
        if not FRANCE_BBOX[1] <= v <= FRANCE_BBOX[3]:
            raise ValueError(f"lat hors bbox France: {v}")
        return v

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError(f"lon hors bornes: {v}")
        if not FRANCE_BBOX[0] <= v <= FRANCE_BBOX[2]:
            raise ValueError(f"lon hors bbox France: {v}")
        return v


def normalize_price(val: Any) -> float | None:
    if val is None:
        return None
    try:
        p = float(val)
    except (TypeError, ValueError):
        return None
    if not PRICE_MIN <= p <= PRICE_MAX:
        return None
    return p


def normalize_outage(debut: Any, rupture_type: Any) -> Outage:
    if debut is None:
        return Outage.none
    if rupture_type == "definitive":
        return Outage.definitive
    return Outage.temporary
