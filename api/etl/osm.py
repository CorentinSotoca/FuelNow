from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("etl.osm")

# Toutes les stations-service OSM de France (nodes + ways + relations, centroides
# pour les surfaces). Le tag `ref:FR:prix-carburants` référence l'id du point de
# vente du flux officiel — c'est la jointure exacte enseigne ↔ station.
OVERPASS_QUERY = (
    "[out:json][timeout:600];"
    'area["ISO3166-1"="FR"][admin_level=2]->.fr;'
    'nwr["amenity"="fuel"](area.fr);'
    "out center tags;"
)

DEFAULT_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter"
)


def overpass_endpoints(raw: str) -> list[str]:
    return [u.strip() for u in raw.split(",") if u.strip()]


@dataclass
class OsmFuelPoiRecord:
    osm_type: str
    osm_id: int
    station_ref: int | None
    brand: str | None
    osm_name: str | None
    lon: float
    lat: float


class OverpassAdapter:
    """Stations-service OpenStreetMap (via Overpass), pour les enseignes.

    - Le tag `ref:FR:prix-carburants` peut contenir plusieurs ids séparés par
      « ; » : on émet un enregistrement par id (jointure exacte en SQL).
    - Un POI sans enseigne (`brand`) ni nom (`name`) est ignoré : rien à
      afficher pour l'utilisateur.
    """

    def __init__(self, elements: list[dict[str, Any]]):
        self._elements = elements

    @classmethod
    async def fetch(cls, urls: list[str], *, timeout: float = 900.0) -> OverpassAdapter:
        """POST vers Overpass, avec fallback d'endpoint et retry réseau.

        - User-Agent explicite obligatoire : overpass-api.de répond 406 au
          UA par défaut de httpx.
        - Overpass peut renvoyer HTTP 200 avec des résultats PARTIELS
          (timeout/mémoire serveur), signalés par un champ `remark` → on
          refuse et on bascule sur l'endpoint suivant.
        - Overpass rate-limit fréquemment (429) : retry avec backoff.
        """
        data = {"data": OVERPASS_QUERY}
        headers = {"User-Agent": "FuelNow-ETL/1.0 (https://fuelnow.squale.ovh)"}
        last_error: str | None = None

        for url in urls:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for attempt in range(3):
                    try:
                        resp = await client.post(url, data=data, headers=headers)
                    except httpx.TransportError as e:
                        last_error = f"{url}: {e}"
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        break
                    if resp.status_code == 200:
                        payload = resp.json()
                        remark = payload.get("remark")
                        if remark:
                            last_error = f"{url}: résultats partiels ({remark})"
                            break
                        return cls(payload.get("elements", []))
                    last_error = f"{url}: HTTP {resp.status_code}"
                    if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    break

        raise RuntimeError(f"overpass: tous les endpoints ont échoué ({last_error})")

    @property
    def total_elements(self) -> int:
        return len(self._elements)

    def parse(self) -> list[OsmFuelPoiRecord]:
        records: list[OsmFuelPoiRecord] = []

        for el in self._elements:
            osm_type = el.get("type")
            if osm_type not in ("node", "way", "relation"):
                continue

            center = el.get("center") or {}
            try:
                lat = float(el.get("lat", center.get("lat")))
                lon = float(el.get("lon", center.get("lon")))
            except (TypeError, ValueError):
                continue

            tags = el.get("tags") or {}
            brand = (tags.get("brand") or "").strip() or None
            osm_name = (tags.get("name") or "").strip() or None
            if brand is None and osm_name is None:
                continue

            osm_id = el.get("id")
            if not isinstance(osm_id, int):
                continue

            refs: list[int | None] = []
            for ref in (tags.get("ref:FR:prix-carburants") or "").split(";"):
                ref = ref.strip()
                if not ref:
                    continue
                try:
                    refs.append(int(ref))
                except ValueError:
                    continue
            if not refs:
                refs = [None]

            for ref in refs:
                records.append(
                    OsmFuelPoiRecord(
                        osm_type=osm_type,
                        osm_id=osm_id,
                        station_ref=ref,
                        brand=brand,
                        osm_name=osm_name,
                        lon=lon,
                        lat=lat,
                    )
                )

        return records
