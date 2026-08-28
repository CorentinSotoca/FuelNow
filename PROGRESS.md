# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 10/10 — Finitions ✅ + étape 11 (responsive + marqueurs prix) ✅
- Statut : terminé
- Dernière vérif : prod stack 4 services healthy, TypeScript 0 erreur, smoke test nginx:8080 OK.

## À faire maintenant (prochaine action concrète)
- Rien — projet complet. Évolutions possibles : historique des prix, isochrones OSRM, alertes utilisateur.

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
- Frontend : `web/` Vite + React-TS + maplibre-gl v6. `MapView` (carte OSM, clic/drag point, cercle GeoJSON, **marqueurs HTML** avec prix affiché directement sur la carte — badges colorés par quartile via `quartileColor()`, cliquables + hover, style appliqué in-place via `applyStationElStyle` pour ne pas casser le transform MapLibre), `FuelSelect`, `RadiusControl`, `ResultsList` + `StationCard` (rang, prix, delta, distance, adresse, badge autoroute, MAJ, itinéraire OSM), `useDebouncedSearch` (400 ms, race-condition safe via reqId), `utils.ts` (quartiles, formatage prix/distance/MAJ). États : loading/empty (élargir +5 km)/error réseau+retry/429/stale banner. Tri prix|distance. **Responsive mobile** : bottom sheet 3 positions (collapsed/half/full) avec handle cliquable + résumé peek (nb stations + prix min), bouton géoloc 📍, controls compacts, `@media (max-width: 768px)`. **Piège maplibre-gl v6 + Vite** : `optimizeDeps.exclude: ['maplibre-gl']`. **Piège marqueurs HTML MapLibre** : ne pas mettre `transform: translate(-50%,-50%)` dans le style de l'élément — MapLibre gère lui-même le positionnement via transform ; ne pas utiliser `replaceWith` pour mettre à jour un marker existant — appliquer les styles in-place sur `marker.getElement()`. **Piège TypeScript** : `erasableSyntaxOnly` → `false`.
- Prod : `docker-compose.prod.yml` (db, api, etl, web). `api/Dockerfile` (user non-root, uvicorn). `api/Dockerfile.etl` (supercronic + entrypoint.sh). `web/Dockerfile` (multi-stage Vite build → nginx alpine). `web/nginx.conf` (SPA fallback + proxy /api + /health). **Piège supercronic** : (1) format crontab = 6 champs (sec min hour dom mon dow), pas 5 comme cron classique → entrypoint.sh préfixe "0 " si 5 champs. (2) supercronic en PID 1 crash sur "Failed to fork exec: no such file or directory" à cause du reaping → flag `-no-reap`. (3) Pas de substitution de variables d'env dans le crontab → entrypoint.sh génère le fichier au runtime.

## Décisions figées (ne pas rediscuter)
- Pas d'historique de prix en v1.
- Stations sans prix exclues par défaut ; ruptures temporaires et définitives exclues.
- Remplacement complet des données à chaque run, en une transaction.
- 6 carburants : gazole, sp95, sp98, e10, e85, gplc.
- Prix bornés [0.5, 5.0] € ; geom hors bbox France rejeté.
- ENUMs créés manuellement dans la migration (postgresql.ENUM avec create_type=False).

## Commandes utiles
- Dev : `docker compose up -d db && docker compose run --rm api alembic upgrade head`
- Dev ETL : `docker compose run --rm etl python -m etl.run`
- Dev tests : `docker compose run --rm api pytest tests/ -q`
- Prod : `docker compose -f docker-compose.prod.yml up -d --build`
- Prod migration : `docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head`
- Prod ETL manuel : `docker compose -f docker-compose.prod.yml run --rm etl python -m etl.run`

## Étapes
- [x] 0 Bootstrap repo
- [x] 1 Docker db
- [x] 2 Schéma DB + migrations
- [x] 3 ETL fetch + parse
- [x] 4 ETL chargement atomique
- [x] 5 API search
- [x] 6 Durcissement API
- [x] 7 Frontend carte
- [x] 8 Frontend résultats
- [x] 9 Prod compose
- [x] 10 Finitions          ✅
- [x] 11 Responsive + marqueurs prix ✅

## Journal (3 dernières entrées)
- 2026-08-28 — étape 11 : responsive mobile (bottom sheet 3 positions : collapsed/half/full, handle cliquable, résumé peek avec nb stations + prix min, bouton géoloc 📍). Marqueurs HTML avec prix affiché directement sur la carte (badges colorés par quartile, cliquables + hover). Remplacement des layers GeoJSON circle+symbol par marqueurs HTML MapLibre (plus de dépendance glyphs externe). Fix bug hover : ne pas écraser le transform MapLibre avec translate(-50%,-50%), utiliser applyStationElStyle in-place au lieu de replaceWith.
- 2026-08-28 — étape 10 : README.md (architecture, quickstart dev+prod, endpoints, env vars, commandes). .dockerignore pour api/ et web/. 24 tests verts. Smoke test prod OK (nginx:8080, 4 services healthy). Projet complet.
- 2026-08-28 — étape 9 : docker-compose.prod.yml (4 services). api/Dockerfile (user non-root). api/Dockerfile.etl (supercronic + entrypoint.sh). web/Dockerfile (multi-stage Vite → nginx). web/nginx.conf (SPA + proxy /api). 3 pièges supercronic : 6 champs, -no-reap, pas de var subst. Fix TypeScript : erasableSyntaxOnly=false, MapLayerMouseEvent. Smoke test nginx:8080 OK.

## Points ouverts / blocages
- (aucun)
