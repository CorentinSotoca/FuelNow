# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 7/10 — Frontend carte
- Statut : à démarrer
- Dernière vérif : `docker compose run --rm api pytest tests/ -v` → 24 passed (13 ETL + 11 API). Rate limit vérifié manuellement (61e requête/min → 429).

## À faire maintenant (prochaine action concrète)
1. Bootstrap `web/` : Vite + React + TypeScript + MapLibre GL (`npm create vite@latest web -- --template react-ts`).
2. Composant `MapView` : carte OSM plein écran, centre France par défaut (zoom 6), clic pour placer un point, marqueur draggable.
3. Composant `RadiusControl` (slider 0,5–30 km) affichant un cercle GeoJSON autour du point.
4. Composant `FuelSelect` alimenté par `GET /api/fuels`.
5. Vérifier : `npm run dev` → carte OSM affichée, cercle réactif au slider.

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
- Durcissement : `app/limiter.py` (slowapi, clé = X-Forwarded-For sinon IP réelle), ETag/Cache-Control sur `/api/stations/search`, CORS désactivé sauf `CORS_ALLOW_ORIGINS` défini. Tests API dans `api/tests/test_api_search.py` avec fixtures sur IDs sentinelles 900000001-5 (loin des vraies données, nettoyées après chaque test). **Piège pytest-asyncio** : avec un engine SQLAlchemy async créé au niveau module, il faut `asyncio_default_fixture_loop_scope = "session"` et `asyncio_default_test_loop_scope = "session"` dans `pyproject.toml`, sinon erreur asyncpg « another operation is in progress » (event loop différent par test vs connexions du pool liées à la loop de création).

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
- [x] 6 Durcissement API
- [ ] 7 Frontend carte    <-- ici
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 6 : app/limiter.py (slowapi 60/min/IP sur /search), ETag+Cache-Control (304 si If-None-Match), CORS conditionnel. test_api_search.py (11 cas, fixtures sentinelles nettoyées). Fix pytest-asyncio loop scope=session. 24 tests verts au total.
- 2026-08-28 — étape 5 : app/routes/{health,fuels,stations}.py, app/schemas.py, app/status.py. Endpoints /health, /api/fuels, /api/stations/search (ST_DWithin + tri price|distance + pagination + cheapest_delta_eur), /api/stations/{id}. Vérifié en réel sur Paris/gazole.
- 2026-08-28 — étape 4 : etl/load.py (staging tables temp + inserts SQLAlchemy Core par batch, TRUNCATE+INSERT en une transaction), etl/run.py (orchestrateur, etl_runs, garde-fou, alerte webhook optionnelle). Run réel OK : 9785 stations, 55121 prix.

## Points ouverts / blocages
- (aucun)
