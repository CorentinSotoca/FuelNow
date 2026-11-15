from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import structlog
from sqlalchemy import text

from app.config import settings
from app.db import async_session
from etl.adapters import OdsJsonAdapter
from etl.load import (
    check_guardrail,
    get_osm_pois_age_hours,
    load_osm_pois_atomically,
    load_stations_atomically,
    purge_etl_runs,
    rebuild_station_brands,
)
from etl.osm import OverpassAdapter, overpass_endpoints
from etl.runs import cleanup_orphaned_runs, create_run, send_alert, update_run

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger("etl")


async def _ensure_osm_pois_fresh() -> None:
    """Rafraîchit le cache OSM (Overpass) s'il a plus de OSM_REFRESH_DAYS jours.

    Non fatal : en cas d'échec on garde l'ancien cache — les enseignes
    manquent simplement pour les stations nouvellement apparues.
    """
    try:
        async with async_session() as session:
            age_hours = await get_osm_pois_age_hours(session)
        if age_hours is not None and age_hours < settings.osm_refresh_days * 24:
            return

        logger.info("osm_pois_refresh_start", age_hours=age_hours)
        adapter = await OverpassAdapter.fetch(
            overpass_endpoints(settings.overpass_urls),
            timeout=settings.overpass_timeout_s,
        )
        pois = adapter.parse()
        # Garde-fou : ~12k POIs attendus en métropole ; une réponse partielle
        # (résultats outre-mer seulement, miroir dégradé...) est refusée et
        # l'ancien cache conservé.
        if len(pois) < settings.osm_min_pois:
            raise RuntimeError(
                f"Overpass: seulement {len(pois)} POIs parsés "
                f"(minimum attendu {settings.osm_min_pois})"
            )
        logger.info("osm_pois_parsed", count=len(pois), elements=adapter.total_elements)

        async with async_session() as session:
            async with session.begin():
                loaded = await load_osm_pois_atomically(session, pois)
        logger.info("osm_pois_loaded", rows=loaded)
    except Exception as e:
        logger.warning("osm_pois_refresh_failed", error=str(e))


async def run_etl() -> None:
    started_at = datetime.now(UTC)
    logger.info("etl_started")

    run_id = await create_run(started_at, source="fr")
    await cleanup_orphaned_runs(source="fr")

    try:
        adapter = await OdsJsonAdapter.fetch(
            settings.source_dataset_url,
        )

        stations = list(adapter.iter_stations())
        count = len(stations)
        rejected = adapter.rejected_count
        logger.info("stations_parsed", count=count, rejected=rejected)

        async with async_session() as session:
            ok = await check_guardrail(
                session, count, settings.etl_min_rows, settings.etl_min_ratio
            )
            await session.commit()

        if not ok:
            msg = f"Guardrail failed: {count} stations below threshold"
            logger.error("guardrail_failed", count=count)
            await update_run(run_id, "failed", error=msg, finished_at=datetime.now(UTC))
            await send_alert(msg, label="ETL")
            return

        # Cache OSM des enseignes : téléchargé hors transaction principale
        # (lent, hebdomadaire, non fatal).
        await _ensure_osm_pois_fresh()

        async with async_session() as session:
            async with session.begin():
                rows_st, rows_pr = await load_stations_atomically(session, stations)
                # Même transaction que le swap des stations : les enseignes
                # restent cohérentes avec les nouvelles stations, sans fenêtre
                # où station_brands serait vide pour le lecteur.
                brands = await rebuild_station_brands(session)
                await session.execute(text("ANALYZE stations"))
                await session.execute(text("ANALYZE station_prices"))
                await session.execute(text("ANALYZE station_brands"))
                await purge_etl_runs(session)

            logger.info("load_complete", rows_stations=rows_st, rows_prices=rows_pr, brands=brands)
            await update_run(
                run_id,
                "success",
                rows_stations=rows_st,
                rows_prices=rows_pr,
                finished_at=datetime.now(UTC),
            )

    except Exception as e:
        logger.exception("etl_failed", error=str(e))
        await update_run(run_id, "failed", error=str(e), finished_at=datetime.now(UTC))
        await send_alert(str(e), label="ETL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_etl())
