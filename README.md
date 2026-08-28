# FuelNow

Trouvez les stations-service les moins chères autour de vous. Carte interactive OpenStreetMap, données carburants mises à jour quotidiennement depuis le flux officiel **Prix des carburants en France – flux instantané v2** (data.economie.gouv.fr).

## Stack

| Couche | Techno |
|---|---|
| Base de données | PostgreSQL 16 + PostGIS 3.4 |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · asyncpg |
| ETL | Python · httpx · SQLAlchemy Core · supercronic (cron 06:00) |
| Frontend | React 19 · TypeScript · Vite 8 · MapLibre GL JS v6 |
| Prod | Docker Compose · nginx (SPA + reverse proxy) |

## Démarrage rapide (dev)

```bash
# 1. Configurer l'environnement
cp .env.example .env
# Éditer .env (mot de passe DB, etc.)

# 2. Lancer la base de données
docker compose up -d db

# 3. Appliquer les migrations
docker compose run --rm api alembic upgrade head

# 4. Premier chargement ETL (~10 000 stations)
docker compose run --rm etl python -m etl.run

# 5. Lancer l'API
docker compose up -d api

# 6. Lancer le frontend (dev server Vite)
cd web && npm install && npm run dev
# → http://localhost:5173
```

## Démarrage prod (un seul VPS)

```bash
cp .env.example .env
# Éditer .env : POSTGRES_PASSWORD, CORS_ALLOW_ORIGINS, etc.

docker compose -f docker-compose.prod.yml up -d --build

# Migration initiale
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# Premier chargement ETL
docker compose -f docker-compose.prod.yml run --rm etl python -m etl.run
```

L'application est disponible sur `http://localhost:8080` (nginx sert la SPA + proxy `/api` vers FastAPI).

## Architecture

```
                    Internet
                       |
                  [ nginx :8080 ]
                   /          \
         / (static)           \ /api/*
    [ web ]                  [ api ]
    nginx + SPA React        FastAPI (uvicorn)
    MapLibre GL + OSM             |
                                  | SQL (asyncpg)
                                  v
    [ etl ] --- pull HTTPS --> [ db ] postgres + PostGIS
    supercronic 06:00              volume pgdata
```

- **ETL** : fetch gzip JSON → validation Pydantic → dépivot 6 carburants → garde-fou (80% du dernier run) → staging tables → `TRUNCATE`+`INSERT` atomique.
- **API** : `ST_DWithin` + `ST_Distance` sur `geography` (index GiST). Rate limit 60/min/IP, ETag + Cache-Control 900s.
- **Frontend** : debounce 400ms, marqueurs HTML colorés par quartile de prix avec prix affiché directement sur la carte, liaison liste↔carte, popup, itinéraire OSM. Responsive mobile : bottom sheet 3 positions, bouton géoloc.

## Endpoints API

| Endpoint | Description |
|---|---|
| `GET /health` | Statut, dernière mise à jour ETL, `stale` (seuil 26h) |
| `GET /api/fuels` | Liste des 6 carburants |
| `GET /api/stations/search` | Recherche par rayon (`lat`, `lon`, `radius_m`, `fuel`, `sort`, pagination) |
| `GET /api/stations/{id}` | Détail d'une station (tous carburants, services, horaires) |

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `POSTGRES_DB` | `fuelnow` | Nom de la base |
| `POSTGRES_USER` | `fuelnow` | Utilisateur DB |
| `POSTGRES_PASSWORD` | `changeme` | Mot de passe DB |
| `DATABASE_URL` | — | URL SQLAlchemy async (construite depuis les vars ci-dessus) |
| `SOURCE_DATASET_URL` | — | URL du dataset ODS (export JSON gzip) |
| `ETL_CRON` | `0 6 * * *` | Schedule cron (format 5 champs, supercronic ajoute les secondes) |
| `ETL_MIN_ROWS` | `5000` | Seuil minimum absolu de stations |
| `ETL_MIN_RATIO` | `0.8` | Ratio minimum vs dernier run réussi |
| `RATE_LIMIT_PER_MIN` | `60` | Requêtes/min/IP sur `/search` |
| `SEARCH_RADIUS_MAX_M` | `30000` | Rayon max (mètres) |
| `CACHE_TTL_S` | `900` | TTL Cache-Control sur `/search` |
| `LOG_LEVEL` | `INFO` | Niveau de log |
| `CORS_ALLOW_ORIGINS` | (vide) | Origines CORS séparées par virgules (vide = désactivé) |
| `ALERT_WEBHOOK_URL` | (vide) | Webhook d'alerte (Discord/ntfy) si ETL échoue |

## Commandes utiles

```bash
# Tests
docker compose run --rm api pytest tests/ -q

# ETL manuel
docker compose run --rm etl python -m etl.run

# Logs ETL
docker compose logs -f etl

# Accéder à la DB
docker compose exec db psql -U fuelnow -d fuelnow
```

## Carburants supportés

Gazole · SP95 · SP98 · E10 · E85 · GPLc

## Source des données

[Prix des carburants en France – flux instantané v2](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/) — data.economie.gouv.fr / Opendatasoft. Cartes © OpenStreetMap contributors.
