from __future__ import annotations

from sqlalchemy import bindparam, text

from app.db import async_session
from etl.load import load_osm_pois_atomically, rebuild_station_brands
from etl.osm import OsmFuelPoiRecord

# Sentinelles au milieu du golfe de Guinée (0,0), loin des vraies stations.
BRAND_STATION_IDS = [900000200, 900000201, 900000202]
BRAND_POI_OSM_IDS = [910000200, 910000201, 910000202]

# id station, lon, lat
STATIONS = [
    (900000200, 0.010, 0.010),  # POI avec ref exacte → match 'ref'
    (900000201, 0.020, 0.020),  # POI sans ref, même position → match 'nearby'
    (900000202, 0.030, 0.030),  # POI le plus proche à ~330 m → aucun match
]

# osm_id, station_ref, brand, osm_name, lon, lat
POIS = [
    (910000200, 900000200, "Enseigne Exacte", None, 0.010, 0.010),
    (910000201, None, "Enseigne Proche", "Station Proche", 0.020, 0.020),
    (910000202, None, "Enseigne Lointaine", None, 0.030, 0.033),
]


class _Rollback(Exception):
    """Sentinel exception to force transaction rollback in load tests."""


async def _seed() -> None:
    async with async_session() as session:
        await session.execute(
            text(
                "INSERT INTO stations (id, address, city, postal_code, road_type, geom) "
                "VALUES (:id, 'Test', 'Test', '00000', 'R', ST_MakePoint(:lon, :lat)::geography) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            [
                {"id": sid, "lon": lon, "lat": lat}
                for sid, lon, lat in STATIONS
            ],
        )
        await session.execute(
            text(
                "INSERT INTO osm_fuel_pois (osm_type, osm_id, station_ref, brand, osm_name, geom, updated_at) "
                "VALUES ('node', :osm_id, :ref, :brand, :name, ST_MakePoint(:lon, :lat)::geography, now())"
            ),
            [
                {"osm_id": osm_id, "ref": ref, "brand": brand, "name": name, "lon": lon, "lat": lat}
                for osm_id, ref, brand, name, lon, lat in POIS
            ],
        )
        await session.commit()


async def _cleanup() -> None:
    async with async_session() as session:
        await session.execute(text("DELETE FROM station_brands WHERE station_id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ), {"ids": BRAND_STATION_IDS})
        await session.execute(text("DELETE FROM osm_fuel_pois WHERE osm_id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ), {"ids": BRAND_POI_OSM_IDS})
        await session.execute(text("DELETE FROM stations WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ), {"ids": BRAND_STATION_IDS})
        await session.commit()


async def test_rebuild_station_brands_exact_ref_then_nearby():
    await _seed()
    try:
        async with async_session() as session:
            try:
                async with session.begin():
                    counts = await rebuild_station_brands(session)

                    result = await session.execute(
                        text(
                            "SELECT station_id, brand, osm_name, match_type FROM station_brands "
                            "WHERE station_id IN :ids ORDER BY station_id"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"ids": BRAND_STATION_IDS},
                    )
                    rows = result.mappings().all()

                    # 900000202 (POI à ~330 m > 150 m) ne matche pas
                    assert len(rows) == 2
                    by_id = {r["station_id"]: r for r in rows}

                    # Match exact par ref:FR:prix-carburants, priorité sur le nearby
                    assert by_id[900000200]["brand"] == "Enseigne Exacte"
                    assert by_id[900000200]["match_type"] == "ref"

                    # Fallback par proximité (< 150 m)
                    assert by_id[900000201]["brand"] == "Enseigne Proche"
                    assert by_id[900000201]["osm_name"] == "Station Proche"
                    assert by_id[900000201]["match_type"] == "nearby"

                    assert counts["total"] >= 2

                    # Force rollback pour préserver les données réelles
                    # (rebuild_station_brands a TRUNCATE puis reconstruit).
                    raise _Rollback
            except _Rollback:
                pass
    finally:
        await _cleanup()


async def test_load_osm_pois_atomically_replaces_cache():
    await _seed()
    try:
        async with async_session() as session:
            try:
                async with session.begin():
                    pois = [
                        OsmFuelPoiRecord(
                            osm_type="node",
                            osm_id=910000200,
                            station_ref=900000200,
                            brand="Nouvelle Enseigne",
                            osm_name=None,
                            lon=0.010,
                            lat=0.010,
                        ),
                        OsmFuelPoiRecord(
                            osm_type="way",
                            osm_id=910000299,
                            station_ref=None,
                            brand=None,
                            osm_name="POI Nomme",
                            lon=0.040,
                            lat=0.040,
                        ),
                    ]
                    loaded = await load_osm_pois_atomically(session, pois)
                    assert loaded == 2

                    # Le cache a été intégralement remplacé : seuls les 2 nouveaux POIs
                    result = await session.execute(text(
                        "SELECT osm_id, station_ref, brand, osm_name, osm_type FROM osm_fuel_pois ORDER BY osm_id"
                    ))
                    rows = result.mappings().all()
                    assert [r["osm_id"] for r in rows] == [910000200, 910000299]
                    by_id = {r["osm_id"]: r for r in rows}
                    assert by_id[910000200]["brand"] == "Nouvelle Enseigne"
                    assert by_id[910000200]["station_ref"] == 900000200
                    assert by_id[910000299]["osm_name"] == "POI Nomme"
                    assert by_id[910000299]["osm_type"] == "way"

                    # Force rollback pour préserver les données réelles
                    # (load_osm_pois_atomically a TRUNCATE le cache).
                    raise _Rollback
            except _Rollback:
                pass
    finally:
        await _cleanup()
