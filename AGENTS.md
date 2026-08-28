# AGENTS.md — FuelNow

## Vue d'ensemble

FuelNow est une application web dockerisée qui permet de trouver les stations-service les moins chères autour d'un point donné. Données carburants rafraîchies quotidiennement depuis le flux officiel **Prix des carburants en France – flux instantané v2** (data.economie.gouv.fr / Opendatasoft). En zone belge, affichage des prix maximum réglementés depuis **Statbel/be.STAT**.

## Stack

| Couche | Techno |
|---|---|
| Base de données | PostgreSQL 16 + PostGIS 3.4 |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · asyncpg |
| ETL | Python · httpx · SQLAlchemy Core · supercronic (cron FR 06:00, BE 07:00) |
| Frontend | React 19 · TypeScript · Vite 8 · MapLibre GL JS v6 |
| Prod | Docker Compose · nginx (SPA + reverse proxy) |

## Structure du repo

```
api/                  FastAPI + ETL (même image Python)
  app/                Application FastAPI
    routes/           health, fuels, stations, be
    config.py         Settings (env vars)
    db.py             Engine SQLAlchemy async
    limiter.py        Rate limit slowapi
    schemas.py        Pydantic models
    status.py         last_success_at / stale (seuil 26h, filtré par source='fr')
  etl/                Pipeline ETL
    adapters.py       OdsJsonAdapter (fetch + dépivot)
    be_adapter.py     StatbelAdapter (fetch + parse prix max BE)
    models.py         StationRecord, StationPriceRecord, Fuel, Outage
    load.py           staging tables + TRUNCATE/INSERT atomique
    runs.py           Shared helpers (create_run, update_run, send_alert, cleanup_orphaned_runs)
    run.py            Orchestrateur FR + etl_runs (source='fr')
    be_run.py         Orchestrateur BE + etl_runs (source='be')
    entrypoint.sh     supercronic (-no-reap, génère crontab au runtime, 2 entries FR+BE)
  tests/              Tests (13 ETL parse + 11 API search + 10 BE adapter + 5 BE API + 7 ETL load)
                      conftest.py (fixtures partagées: db_session, cleanup helpers)
  alembic/            Migrations
web/                  SPA React + Vite
  src/
    App.tsx           Layout (sidebar + map + bottom sheet mobile)
    App.css           Tous les styles (incl. responsive @media 768px)
    components/       MapView, FuelSelect, RadiusControl, ResultsList, StationCard, BeMaxPricePanel, ErrorBoundary
    hooks/            useDebouncedSearch (400ms, race-condition safe, détection zone BE)
    api.ts            Client API (ApiError, fetchFuels, searchStations, fetchBePrices)
    types.ts          Types TypeScript
    utils.ts          Quartiles, formatage prix/distance/MAJ, isNearBelgium (polygone), formatBeDate
    geo.ts            Génération cercle GeoJSON
docs/ARCHITECTURE.md  Architecture technique détaillée
docker-compose.yml    Dev (db, api, etl)
docker-compose.prod.yml  Prod (db, api, etl, web)
deploy.sh             Script de déploiement (git pull → build → migrations → restart)
.github/workflows/ci.yml  CI GitHub Actions (lint, tests, frontend, security, docker-build)
.env.example          Template variables d'environnement
```

## Commandes

```bash
# Dev
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose run --rm etl python -m etl.run
docker compose run --rm etl python -m etl.be_run
docker compose up -d api
cd web && npm install && npm run dev   # → localhost:5173

# Tests
docker compose run --rm api pytest tests/ -q   # 46 tests

# Prod
docker compose -f docker-compose.prod.yml up -d --build db
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml run --rm etl python -m etl.run
docker compose -f docker-compose.prod.yml up -d api web
# → http://localhost:8080

# Mise à jour
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# TypeScript check
cd web && npx tsc --noEmit
```

## Endpoints API

| Endpoint | Description |
|---|---|
| `GET /health` | Statut, dernière mise à jour ETL, `stale` (seuil 26h) |
| `GET /api/fuels` | Liste des 6 carburants |
| `GET /api/stations/search` | Recherche par rayon (`lat`, `lon`, `radius_m`, `fuel`, `sort`, pagination) |
| `GET /api/stations/{id}` | Détail d'une station |
| `GET /api/be/prices` | Prix maximum officiels Belgique (filtre optionnel `fuel`) |

## Variables d'environnement

Voir `.env.example`. Les critiques : `POSTGRES_PASSWORD`, `DATABASE_URL` (obligatoire, à construire manuellement), `SOURCE_DATASET_URL`, `STATBEL_API_URL`, `CORS_ALLOW_ORIGINS`, `ETL_CRON`, `ETL_BE_CRON`, `WEB_PORT`.

## Décisions figées

- Pas d'historique de prix en v1.
- Stations sans prix exclues par défaut ; ruptures temporaires et définitives exclues.
- Remplacement complet des données à chaque run ETL, en une transaction.
- 6 carburants : gazole, sp95, sp98, e10, e85, gplc.
- Prix bornés [0.5, 5.0] € ; geom hors bbox France rejeté (BBOX très large : -65/-25/20/55 pour inclure DROM et frontières).
- ENUMs créés manuellement dans la migration (postgresql.ENUM avec `create_type=False`).
- Belgique : pas d'open data par station, seuls les prix maximum réglementés (Statbel) sont affichés.
- `etl_runs.source` distingue les runs FR (`source='fr'`) des runs BE (`source='be'`).
- `be_max_prices.fuel_code` est un TEXT simple, indépendant de l'ENUM `fuel_type`.
- Belgique : affichage hybride — les stations FR frontalières restent visibles, le panneau BE s'affiche en plus.
- Détection zone belge : `isNearBelgium()` dans `utils.ts` utilise un **polygone** (ray-casting) qui suit la frontière franco-belge + ~20 km de tampon côté français, **pas** une bbox rectangulaire (une bbox inclurait faussement Arras, Cambrai, etc.).

## Pièges et gotchas

### ETL

- **Jamais de SQL par interpolation de chaînes** (problèmes de quoting JSON) — toujours passer par des paramètres liés.
- **Jamais `func.now()` dans des params `executemany`** — asyncpg attend une vraie valeur Python → utiliser `datetime.now(UTC)`.
- Dataset source : utiliser `geom {lon, lat}`, **PAS** `latitude`/`longitude` (entiers ×100000).
- Modèle source « wide » (1 colonne par carburant) → l'ETL le dépivote en table longue `station_prices`.
- **structlog** : les scripts ETL (`run.py`, `be_run.py`) utilisent structlog pour le logging JSON structuré (pas le module logging standard).
- **Retry réseau** : `OdsJsonAdapter.fetch` et `StatbelAdapter.fetch` retentent 3 fois sur `httpx.TransportError` avec backoff exponentiel.
- **Runs orphelins** : `cleanup_orphaned_runs()` est appelé au démarrage de chaque ETL pour marquer `failed` les runs restés `running` (crash).

### API

- Requête search en SQL brut (CTE `filtered`+`agg`) car ORM peu adapté à `ST_DWithin`/`ST_Distance`/agrégats de fenêtre.
- `order_by` choisi en Python selon `sort` (valeur restreinte par `Literal`, donc pas d'injection) puis formaté dans le template SQL.
- **Piège pytest-asyncio** : avec un engine SQLAlchemy async créé au niveau module, il faut `asyncio_default_fixture_loop_scope = "session"` et `asyncio_default_test_loop_scope = "session"` dans `pyproject.toml`, sinon erreur asyncpg « another operation in progress ».
- Tests API : fixtures sur IDs sentinelles 900000001-5 (loin des vraies données, nettoyées après chaque test).
- **Rate limit** : `slowapi` sur **tous** les endpoints (`/health`, `/search`, `/stations/{id}`, `/be/prices`), pas seulement `/search`.
- **IP réelle** : le rate limiter lit `X-Real-IP` (positionné par nginx), pas le premier élément de `X-Forwarded-For` (spoofable).
- **pool_pre_ping** : l'engine SQLAlchemy a `pool_pre_ping=True` + `pool_recycle=3600` pour détecter les connexions mortes.

### Frontend

- **maplibre-gl v6 + Vite** : `optimizeDeps.exclude: ['maplibre-gl']` dans `vite.config.ts` pour fix le worker URL en dev. **En prod (build)**, il faut en plus appeler `setWorkerUrl()` avec un import `maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url` (voir `MapView.tsx`) — sans ça, le worker n'est pas extrait par Vite, la source GeoJSON du cercle ne s'affiche jamais (404 silencieux sur `maplibre-gl-worker.mjs`).
- **Cercle de rayon** : source GeoJSON `search-radius` + 2 layers (`fill` + `line` pointillés) alimentées par `circleGeoJSON()` dans `geo.ts`. Se met à jour via `useEffect` sur `[point, radiusM]`.
- **Bouton itinéraire** : utilise un URI `geo:lat,lon?q=lat,lon(Label)` (RFC 5870) — s'ouvre dans l'app de maps par défaut sur mobile. Pas de `target="_blank"`.
- **Popup station** : affiche prix, adresse, code postal + ville, distance.
- **Marqueurs HTML MapLibre** : ne **pas** mettre `transform: translate(-50%,-50%)` dans le style de l'élément — MapLibre gère lui-même le positionnement. Ne **pas** utiliser `replaceWith` pour mettre à jour un marker — appliquer les styles in-place sur `marker.getElement()` via `applyStationElStyle`.
- **TypeScript** : `erasableSyntaxOnly: false` dans `tsconfig.app.json` (bloque les classes avec param properties comme ApiError).
- Classes CSS popup en maplibre-gl v6 : préfixées `maplibregl-` (pas `maplibre-`).
- **Zone belge** : `isNearBelgium(lat, lon)` dans `utils.ts` utilise un polygone (algorithme du ray-casting) qui suit la frontière franco-belge + ~20 km de tampon côté français. Une bbox rectangulaire ne fonctionne pas car elle inclurait des villes françaises éloignées de la frontière (Arras, Cambrai, Béthune, Lens, Douai). Le polygone exclut ces villes tout en incluant Lille, Valenciennes, Maubeuge, Dunkerque, Hirson, Givet. Quand `isNearBelgium` est vrai, le hook `useDebouncedSearch` fetch les prix BE via `GET /api/be/prices` et `BeMaxPricePanel` s'affiche en haut des résultats. Les stations FR frontalières restent visibles (affichage hybride).

### Supercronic (ETL)

1. Format crontab = **6 champs** (sec min hour dom mon dow), pas 5 → `entrypoint.sh` préfixe "0 " si 5 champs.
2. supercronic en PID 1 crash sur "Failed to fork exec" → flag **`-no-reap`**.
3. Pas de substitution de variables d'env dans le crontab → `entrypoint.sh` génère le fichier au runtime.
4. Deux entries : FR (`etl.run`) et BE (`etl.be_run`).

### Responsive mobile

- Bottom sheet 3 positions : `collapsed` / `half` / `full` (handle cliquable pour cycler).
- Résumé peek en mode replié : nb stations + prix min (ou prix max BE si en zone belge).
- Bouton géoloc 📍 pour se positionner sans cliquer sur la carte.
- `@media (max-width: 768px)` dans `App.css`.

## Source des données

[Prix des carburants en France – flux instantané v2](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/) — data.economie.gouv.fr / Opendatasoft. Cartes © OpenStreetMap contributors.

Prix maximum officiels Belgique : [Statbel/be.STAT](https://bestat.economie.fgov.be/bestat/api/views/9e9cf394-6c54-4d81-8013-7124a8c4bf15/result/JSON).
