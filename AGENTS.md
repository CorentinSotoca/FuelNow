# AGENTS.md — FuelNow

## Vue d'ensemble

FuelNow est une application web dockerisée qui permet de trouver les stations-service les moins chères autour d'un point donné. Données carburants rafraîchies quotidiennement depuis le flux officiel **Prix des carburants en France – flux instantané v2** (data.economie.gouv.fr / Opendatasoft).

## Stack

| Couche | Techno |
|---|---|
| Base de données | PostgreSQL 16 + PostGIS 3.4 |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · asyncpg |
| ETL | Python · httpx · SQLAlchemy Core · supercronic (cron 06:00) |
| Frontend | React 19 · TypeScript · Vite 8 · MapLibre GL JS v6 |
| Prod | Docker Compose · nginx (SPA + reverse proxy) |

## Structure du repo

```
api/                  FastAPI + ETL (même image Python)
  app/                Application FastAPI
    routes/           health, fuels, stations
    config.py         Settings (env vars)
    db.py             Engine SQLAlchemy async
    limiter.py        Rate limit slowapi
    schemas.py        Pydantic models
    status.py         last_success_at / stale (seuil 26h)
  etl/                Pipeline ETL
    adapters.py       OdsJsonAdapter (fetch + dépivot)
    models.py         StationRecord, StationPriceRecord, Fuel, Outage
    load.py           staging tables + TRUNCATE/INSERT atomique
    run.py            Orchestrateur + etl_runs
    entrypoint.sh     supercronic (-no-reap, génère crontab au runtime)
  tests/              24 tests (13 ETL parse + 11 API search)
  alembic/            Migrations
web/                  SPA React + Vite
  src/
    App.tsx           Layout (sidebar + map + bottom sheet mobile)
    App.css           Tous les styles (incl. responsive @media 768px)
    components/       MapView, FuelSelect, RadiusControl, ResultsList, StationCard
    hooks/            useDebouncedSearch (400ms, race-condition safe)
    api.ts            Client API (ApiError, fetchFuels, searchStations)
    types.ts          Types TypeScript
    utils.ts          Quartiles, formatage prix/distance/MAJ
    geo.ts            Génération cercle GeoJSON
docs/ARCHITECTURE.md  Architecture technique détaillée
docker-compose.yml    Dev (db, api, etl)
docker-compose.prod.yml  Prod (db, api, etl, web)
.env.example          Template variables d'environnement
```

## Commandes

```bash
# Dev
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose run --rm etl python -m etl.run
docker compose up -d api
cd web && npm install && npm run dev   # → localhost:5173

# Tests
docker compose run --rm api pytest tests/ -q   # 24 tests

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

## Variables d'environnement

Voir `.env.example`. Les critiques : `POSTGRES_PASSWORD`, `DATABASE_URL` (obligatoire, à construire manuellement), `SOURCE_DATASET_URL`, `CORS_ALLOW_ORIGINS`, `ETL_CRON`, `WEB_PORT`.

## Décisions figées

- Pas d'historique de prix en v1.
- Stations sans prix exclues par défaut ; ruptures temporaires et définitives exclues.
- Remplacement complet des données à chaque run ETL, en une transaction.
- 6 carburants : gazole, sp95, sp98, e10, e85, gplc.
- Prix bornés [0.5, 5.0] € ; geom hors bbox France rejeté.
- ENUMs créés manuellement dans la migration (postgresql.ENUM avec `create_type=False`).

## Pièges et gotchas

### ETL

- **Jamais de SQL par interpolation de chaînes** (problèmes de quoting JSON) — toujours passer par des paramètres liés.
- **Jamais `func.now()` dans des params `executemany`** — asyncpg attend une vraie valeur Python → utiliser `datetime.now(timezone.utc)`.
- Dataset source : utiliser `geom {lon, lat}`, **PAS** `latitude`/`longitude` (entiers ×100000).
- Modèle source « wide » (1 colonne par carburant) → l'ETL le dépivote en table longue `station_prices`.

### API

- Requête search en SQL brut (CTE `filtered`+`agg`) car ORM peu adapté à `ST_DWithin`/`ST_Distance`/agrégats de fenêtre.
- `order_by` choisi en Python selon `sort` (valeur restreinte par `Literal`, donc pas d'injection) puis formaté dans le template SQL.
- **Piège pytest-asyncio** : avec un engine SQLAlchemy async créé au niveau module, il faut `asyncio_default_fixture_loop_scope = "session"` et `asyncio_default_test_loop_scope = "session"` dans `pyproject.toml`, sinon erreur asyncpg « another operation in progress ».
- Tests API : fixtures sur IDs sentinelles 900000001-5 (loin des vraies données, nettoyées après chaque test).

### Frontend

- **maplibre-gl v6 + Vite** : `optimizeDeps.exclude: ['maplibre-gl']` dans `vite.config.ts` pour fix le worker URL en dev. **En prod (build)**, il faut en plus appeler `setWorkerUrl()` avec un import `maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url` (voir `MapView.tsx`) — sans ça, le worker n'est pas extrait par Vite, la source GeoJSON du cercle ne s'affiche jamais (404 silencieux sur `maplibre-gl-worker.mjs`).
- **Cercle de rayon** : source GeoJSON `search-radius` + 2 layers (`fill` + `line` pointillés) alimentées par `circleGeoJSON()` dans `geo.ts`. Se met à jour via `useEffect` sur `[point, radiusM]`.
- **Bouton itinéraire** : utilise un URI `geo:lat,lon?q=lat,lon(Label)` (RFC 5870) — s'ouvre dans l'app de maps par défaut sur mobile. Pas de `target="_blank"`.
- **Popup station** : affiche prix, adresse, code postal + ville, distance.
- **Marqueurs HTML MapLibre** : ne **pas** mettre `transform: translate(-50%,-50%)` dans le style de l'élément — MapLibre gère lui-même le positionnement. Ne **pas** utiliser `replaceWith` pour mettre à jour un marker — appliquer les styles in-place sur `marker.getElement()` via `applyStationElStyle`.
- **TypeScript** : `erasableSyntaxOnly: false` dans `tsconfig.app.json` (bloque les classes avec param properties comme ApiError).
- Classes CSS popup en maplibre-gl v6 : préfixées `maplibregl-` (pas `maplibre-`).

### Supercronic (ETL)

1. Format crontab = **6 champs** (sec min hour dom mon dow), pas 5 → `entrypoint.sh` préfixe "0 " si 5 champs.
2. supercronic en PID 1 crash sur "Failed to fork exec" → flag **`-no-reap`**.
3. Pas de substitution de variables d'env dans le crontab → `entrypoint.sh` génère le fichier au runtime.

### Responsive mobile

- Bottom sheet 3 positions : `collapsed` / `half` / `full` (handle cliquable pour cycler).
- Résumé peek en mode replié : nb stations + prix min.
- Bouton géoloc 📍 pour se positionner sans cliquer sur la carte.
- `@media (max-width: 768px)` dans `App.css`.

## Source des données

[Prix des carburants en France – flux instantané v2](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/) — data.economie.gouv.fr / Opendatasoft. Cartes © OpenStreetMap contributors.
