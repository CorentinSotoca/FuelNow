from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Protocol

import httpx

from etl.models import (
    FUEL_FIELD_MAP,
    Outage,
    StationPriceRecord,
    StationRecord,
    normalize_outage,
    normalize_price,
)


class SourceAdapter(Protocol):
    def iter_stations(self) -> Iterator[StationRecord]: ...

    @property
    def total_records(self) -> int: ...


def _parse_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except (TypeError, ValueError):
        return None


class OdsJsonAdapter:
    def __init__(self, raw_data: list[dict[str, Any]]):
        self._data = raw_data
        self._rejected = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> OdsJsonAdapter:
        try:
            decompressed = gzip.decompress(data)
        except (gzip.BadGzipFile, OSError):
            decompressed = data
        return cls(json.loads(decompressed))

    @classmethod
    async def fetch(
        cls,
        url: str,
        *,
        timeout: float = 120.0,
    ) -> OdsJsonAdapter:
        headers = {"Accept-Encoding": "gzip"}

        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(3):
                try:
                    resp = await client.get(url, headers=headers)
                except httpx.TransportError:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
                if resp.status_code == 200:
                    return cls.from_bytes(resp.content)
                if resp.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()

        raise RuntimeError("fetch: unreachable — retries exhausted without response")

    @property
    def total_records(self) -> int:
        return len(self._data)

    @property
    def rejected_count(self) -> int:
        return self._rejected

    def iter_stations(self) -> Iterator[StationRecord]:
        for row in self._data:
            try:
                record = self._parse_row(row)
                if record is not None:
                    yield record
                else:
                    self._rejected += 1
            except Exception:
                self._rejected += 1

    def _parse_row(self, row: dict[str, Any]) -> StationRecord | None:
        geom = row.get("geom")
        if not geom or not isinstance(geom, dict):
            return None
        lon = geom.get("lon")
        lat = geom.get("lat")
        if lon is None or lat is None:
            return None

        station_id_raw = row.get("id")
        if station_id_raw is None:
            return None
        try:
            station_id = int(station_id_raw)
        except (TypeError, ValueError):
            return None

        prices: list[StationPriceRecord] = []
        for fuel_key, fuel_enum in FUEL_FIELD_MAP.items():
            price_val = row.get(f"{fuel_key}_prix")
            price_maj = _parse_datetime(row.get(f"{fuel_key}_maj"))
            rupture_debut = row.get(f"{fuel_key}_rupture_debut")
            rupture_type = row.get(f"{fuel_key}_rupture_type")

            price_eur = normalize_price(price_val)
            outage = normalize_outage(rupture_debut, rupture_type)

            has_price = price_eur is not None
            has_outage = outage != Outage.none

            if not has_price and not has_outage:
                continue

            prices.append(
                StationPriceRecord(
                    fuel=fuel_enum,
                    price_eur=price_eur,
                    price_maj=price_maj,
                    outage=outage,
                )
            )

        try:
            return StationRecord(
                id=station_id,
                address=row.get("adresse"),
                postal_code=str(row.get("cp")) if row.get("cp") else None,
                city=row.get("ville"),
                dept_code=row.get("code_departement"),
                dept_name=row.get("departement"),
                region_name=row.get("region"),
                road_type=row.get("pop"),
                lon=float(lon),
                lat=float(lat),
                services={"services": row.get("services_service")} if row.get("services_service") else None,
                opening_hours={"horaires": row.get("horaires")} if row.get("horaires") else None,
                prices=prices,
            )
        except (ValueError, TypeError):
            return None
