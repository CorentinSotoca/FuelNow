from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger("etl.be")

STATBEL_PRODUCT_MAP: dict[str, str] = {
    "Diesel B7 (€/L)": "gazole",
    "Essence 95 RON E5 (€/L)": "sp95",
    "Essence 95 RON E10 (€/L)": "e10",
    "Essence 98 RON E5 (€/L)": "sp98",
    "Autogas LPG (à la pompe) (€/L)": "gplc",
}

_BE_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


@dataclass
class BeMaxPriceRecord:
    fuel_code: str
    product_label: str
    price_eur: float
    price_date: date


def parse_be_date(raw: str) -> date | None:
    raw = raw.strip().upper()
    if len(raw) < 7:
        return None
    day_str = raw[:2]
    month_str = raw[2:5]
    year_str = raw[5:]
    try:
        day = int(day_str)
        month = _BE_MONTH_MAP.get(month_str)
        if month is None:
            return None
        year = int(year_str)
        if year < 100:
            year += 2000
        return date(year, month, day)
    except (ValueError, KeyError):
        return None


class StatbelAdapter:
    def __init__(self, facts: list[dict[str, Any]]):
        self._facts = facts

    @classmethod
    async def fetch(cls, url: str, *, timeout: float = 60.0) -> StatbelAdapter:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for attempt in range(3):
                try:
                    resp = await client.get(url)
                except httpx.TransportError:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
                if resp.status_code == 200:
                    data = resp.json()
                    facts = data.get("facts", []) if isinstance(data, dict) else []
                    return cls(facts)
                if resp.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
        raise RuntimeError("fetch: unreachable — retries exhausted without response")

    def parse(self) -> list[BeMaxPriceRecord]:
        records: list[BeMaxPriceRecord] = []
        for fact in self._facts:
            product = (fact.get("Produit") or "").strip()
            fuel_code = STATBEL_PRODUCT_MAP.get(product)
            if fuel_code is None:
                continue

            price_raw = fact.get("Prix TVA incl.")
            if price_raw is None:
                continue
            try:
                price_eur = float(price_raw)
            except (TypeError, ValueError):
                continue

            date_raw = fact.get("Jour") or ""
            price_date = parse_be_date(date_raw)
            if price_date is None:
                continue

            records.append(BeMaxPriceRecord(
                fuel_code=fuel_code,
                product_label=product,
                price_eur=price_eur,
                price_date=price_date,
            ))
        return records
