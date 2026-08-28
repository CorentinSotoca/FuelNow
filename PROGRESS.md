# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 8/10 — Frontend résultats
- Statut : à démarrer
- Dernière vérif : Playwright headless → 6 boutons carburant, marqueur au clic, slider réactif, cercle GeoJSON rendu, 0 erreur console.

## À faire maintenant (prochaine action concrète)
1. Ajouter `ResultsList` + `StationCard` : déclenchement recherche au debounce 400 ms (point+rayon+carburant), liste triée prix, rang, écart vs moins cher, distance, adresse, badge autoroute, « MAJ il y a Xh », lien itinéraire OSM.
2. Marqueurs stations sur la carte (couleur par quartile de prix), liaison hover/clic liste↔marqueur, popup.
3. États d'erreur : aucun résultat (« élargir le rayon » + bouton +5 km), erreur réseau (retry), `stale=true` → bandeau, 429 → message d'attente.
4. Vérifier : recherche Paris gazole → liste triée cohérente avec `curl` API.

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
- Durcissement : `app/limiter.py` (slowapi, clé = X-Forwarded-For sinon IP réelle), ETag/Cache-Control sur `/api/stations/search`, CORS désactivé sauf `CORS_ALLOW_ORIGINS` défini. Tests API dans `api/tests/test_api_search.py` avec fixtures sur IDs sentinelles 900000001-5 (loin des vraies données, nettoyées après chaque test). **Piège pytest-asyncio** : avec un engine SQLAlchemy async créé au niveau module, il faut `asyncio_default_fixture_loop_scope = "session"` et `asyncio_default_test_loop_scope = "session"` dans `pyproject.toml`, sinon erreur asyncpg « another operation in progress » (event loop différent par test vs connexions du pool liées à la loop de création).
- Frontend : `web/` Vite + React-TS + maplibre-gl v6. `MapView` (carte OSM, clic/drag point, cercle GeoJSON), `FuelSelect`, `RadiusControl`, `api.ts` (client fetch), `geo.ts` (cercle sans turf.js). **Piège maplibre-gl v6 + Vite** : le pré-bundling (optimizeDeps) casse l'URL du Web Worker interne (`maplibre-gl-worker.mjs` → `net::ERR_FAILED` silencieux) ; aucune source GeoJSON ne rend (fill/line) alors que raster/background fonctionne. Fix : `optimizeDeps.exclude: ['maplibre-gl']` dans `vite.config.ts`. Le worker se charge alors depuis `node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs` nativement.

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
- [x] 7 Frontend carte
- [ ] 8 Frontend résultats    <-- ici
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 7 : web/ Vite+React-TS+maplibre-gl v6. MapView (OSM, clic/drag, cercle GeoJSON), FuelSelect, RadiusControl, api.ts, geo.ts. Bug worker maplibre-gl+vite résolu (optimizeDeps.exclude). Vérifié Playwright headless.
- 2026-08-28 — étape 6 : app/limiter.py (slowapi 60/min/IP sur /search), ETag+Cache-Control (304 si If-None-Match), CORS conditionnel. test_api_search.py (11 cas, fixtures sentinelles nettoyées). Fix pytest-asyncio loop scope=session. 24 tests verts au total.
- 2026-08-28 — étape 5 : app/routes/{health,fuels,stations}.py, app/schemas.py, app/status.py. Endpoints /health, /api/fuels, /api/stations/search (ST_DWithin + tri price|distance + pagination + cheapest_delta_eur), /api/stations/{id}. Vérifié en réel sur Paris/gazole.

## Points ouverts / blocages
- (aucun)
