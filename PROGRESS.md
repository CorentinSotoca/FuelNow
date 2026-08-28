# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 6/10 — Durcissement API
- Statut : à démarrer
- Dernière vérif : `curl "localhost:8000/api/stations/search?lat=48.85&lon=2.35&radius_m=3000&fuel=gazole"` → 7 items, prix croissants ; tri `sort=distance` vérifié ; bornes invalides → 422 ; `/api/stations/{id}` inconnu → 404.

## À faire maintenant (prochaine action concrète)
1. Ajouter rate limit `slowapi` (60 req/min/IP) sur `/api/stations/search`.
2. Ajouter `Cache-Control: public, max-age=900` + `ETag` sur `/search`.
3. Écrire `api/tests/test_api_search.py` (bornes, tri, exclusion rupture, pagination) avec fixture DB de test.
4. Logs JSON déjà en place côté ETL (`logging.basicConfig` format JSON) — appliquer le même format à l'API (uvicorn log config).

## Contexte minimal indispensable
- Doc d'architecture : `docs/ARCHITECTURE.md` (à lire avant toute décision).
- Source données : dataset ODS `prix-des-carburants-en-france-flux-instantane-v2`
  sur data.economie.gouv.fr, export JSON **gzip**, modèle wide (1 col/carburant),
  ignorer `latitude`/`longitude` (entiers x100000) → utiliser `geom`.
- Stack figée : PostgreSQL+PostGIS / FastAPI async / React+Vite+MapLibre / Docker Compose.
- DB : docker compose up -d db, migration 001 appliquée.
- ETL parse : `api/etl/models.py` (StationRecord, StationPriceRecord, Fuel, Outage), `api/etl/adapters.py` (OdsJsonAdapter avec fetch async + dépivot). 13 tests verts.
- ETL load : `api/etl/load.py` (staging tables temp + inserts SQLAlchemy Core paramétrés par batch de 500 + TRUNCATE/INSERT en transaction), `api/etl/run.py` (orchestrateur + etl_runs). Point d'attention : ne jamais construire de SQL par interpolation de chaînes (problèmes de quoting JSON) — toujours passer par des paramètres liés ; ne jamais passer `func.now()`/expressions SQL dans des params `executemany` (asyncpg attend une vraie valeur Python) → utiliser `datetime.now(timezone.utc)`.
- API : `app/routes/{health,fuels,stations}.py`, `app/schemas.py` (Pydantic), `app/status.py` (last_success_at/stale partagé, seuil 26h). Requête search en SQL brut (CTE `filtered`+`agg`) car ORM peu adapté à `ST_DWithin`/`ST_Distance`/agrégats de fenêtre ; `order_by` choisi en Python selon `sort` (valeur restreinte par `Literal`, donc pas d'injection) puis formaté dans le template SQL.

## Décisions figées (ne pas rediscuter)
- Pas d'historique de prix en v1.
- Stations sans prix exclues par défaut ; ruptures temporaires et définitives exclues.
- Remplacement complet des données à chaque run, en une transaction.
- 6 carburants : gazole, sp95, sp98, e10, e85, gplc.
- Prix bornés [0.5, 5.0] € ; geom hors bbox France rejeté.
- ENUMs créés manuellement dans la migration (postgresql.ENUM avec create_type=False).

## Commandes utiles
- `docker compose up -d db && docker compose run --rm api alembic upgrade head`
- `docker compose run --rm etl python -m etl.run`
- `docker compose run --rm api pytest tests/ -q`

## Étapes
- [x] 0 Bootstrap repo
- [x] 1 Docker db
- [x] 2 Schéma DB + migrations
- [x] 3 ETL fetch + parse
- [x] 4 ETL chargement atomique
- [x] 5 API search
- [ ] 6 Durcissement API    <-- ici
- [ ] 7 Frontend carte
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 5 : app/routes/{health,fuels,stations}.py, app/schemas.py, app/status.py. Endpoints /health, /api/fuels, /api/stations/search (ST_DWithin + tri price|distance + pagination + cheapest_delta_eur), /api/stations/{id}. Vérifié en réel sur Paris/gazole.
- 2026-08-28 — étape 4 : etl/load.py (staging tables temp + inserts SQLAlchemy Core par batch, TRUNCATE+INSERT en une transaction), etl/run.py (orchestrateur, etl_runs, garde-fou, alerte webhook optionnelle). Run réel OK : 9785 stations, 55121 prix.
- 2026-08-28 — étape 3 : etl/models.py (Pydantic StationRecord + StationPriceRecord, validation lat/lon/prix), etl/adapters.py (OdsJsonAdapter : fetch async gzip, dépivot 6 carburants, rupture temp/def). Fixture ods_sample.json (8 cas). 13 tests verts.

## Points ouverts / blocages
- (aucun)
