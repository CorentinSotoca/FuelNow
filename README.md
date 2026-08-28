# FuelNow

Trouvez les stations-service les moins chères autour de vous. Carte interactive OpenStreetMap, données carburants mises à jour quotidiennement depuis le flux officiel **Prix des carburants en France – flux instantané v2** (data.economie.gouv.fr). A proximité de la Belgique, affichage des prix maximum réglementés depuis **Statbel/be.STAT**.

**Démo en ligne : https://fuelnow.squale.ovh/**

> ⚠️ Ce projet a été intégralement **vibecodé** — généré via des sessions de pair-programming avec un assistant IA. Aucune ligne de code n'a été tapée à la main. Le code n'a pas été relu ni audité manuellement.

## Stack

| Couche | Techno |
|---|---|
| Base de données | PostgreSQL 16 + PostGIS 3.4 |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · asyncpg |
| ETL | Python · httpx · SQLAlchemy Core · supercronic (cron FR 06:00, BE 07:00) |
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

# 5. Premier chargement prix maximum Belgique
docker compose run --rm etl python -m etl.be_run

# 6. Lancer l'API
docker compose up -d api

# 7. Lancer le frontend (dev server Vite)
cd web && npm install && npm run dev
# → http://localhost:5173
```

## Démarrage prod (un seul VPS)

```bash
cp .env.example .env
# Éditer .env : POSTGRES_PASSWORD, CORS_ALLOW_ORIGINS, WEB_PORT, etc.

# 1. Build des images et lancement de la base
docker compose -f docker-compose.prod.yml up -d --build db

# 2. Attendre que la base soit saine
docker compose -f docker-compose.prod.yml wait db

# 3. Appliquer les migrations (création des tables)
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# 4. Premier chargement ETL (~10 000 stations)
docker compose -f docker-compose.prod.yml run --rm etl python -m etl.run

# 5. Premier chargement prix maximum Belgique
docker compose -f docker-compose.prod.yml run --rm etl python -m etl.be_run

# 6. Lancer l'API et le frontend
docker compose -f docker-compose.prod.yml up -d api web
```

L'application est disponible sur `http://localhost:8080` (nginx sert la SPA + proxy `/api` vers FastAPI).

> **Important** : les étapes 3 et 4 doivent être exécutées avant de lancer l'API.
> Sans migrations, `/health` renvoie une 500 (table `etl_runs` manquante).
> Sans ETL, la recherche ne renvoie aucun résultat.

## Mise à jour

### Mise à jour standard

```bash
# 1. Récupérer le code le plus récent
git pull

# 2. Reconstruire les images et relancer les conteneurs
docker compose -f docker-compose.prod.yml up -d --build

# 3. Appliquer les migrations de base de données
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

Les migrations ne font rien si le schéma est déjà à jour. L'ETL FR continue de tourner automatiquement à 06h00 via supercronic, et l'ETL BE à 07h00.

### Vérifier que la mise à jour s'est bien passée

```bash
# L'API répond et les données sont présentes
curl -s http://localhost:8080/health | jq .

# Les conteneurs tournent sans erreur
docker compose -f docker-compose.prod.yml ps

# Logs de l'API (aucune erreur attendue)
docker compose -f docker-compose.prod.yml logs --tail=20 api

# Logs de l'ETL (vérifier le dernier run)
docker compose -f docker-compose.prod.yml logs --tail=20 etl
```

### Rollback (en cas de problème)

```bash
# Revenir à la version précédente
git checkout <hash-du-commit-précédent>
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm api alembic downgrade -1
```

> ⚠️ Le rollback de la base ne fonctionne que si la migration descendante existe et n'est pas destructive. Vérifier le contenu de `api/alembic/versions/` avant de downgrade.

### Mettre à jour uniquement le frontend

Si seuls des fichiers du dossier `web/` ont changé :

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build web
```

Aucune migration ni redémarrage de l'API nécessaire.

### Forcer un rechargement ETL manuellement

```bash
# ETL France (stations-service)
docker compose -f docker-compose.prod.yml run --rm etl python -m etl.run

# ETL Belgique (prix maximum officiels)
docker compose -f docker-compose.prod.yml run --rm etl python -m etl.be_run
```

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

- **ETL** : fetch gzip JSON → validation Pydantic → dépivot 6 carburants → garde-fou (80% du dernier run) → staging tables → `TRUNCATE`+`INSERT` atomique. Un second ETL récupère les prix maximum officiels belges (Statbel) via UPSERT.
- **API** : `ST_DWithin` + `ST_DDistance` sur `geography` (index GiST). Rate limit 60/min/IP sur tous les endpoints (IP réelle via `X-Real-IP`), ETag + Cache-Control 900s. Engine SQLAlchemy avec `pool_pre_ping` + `pool_recycle=3600`.
- **Frontend** : debounce 400ms, marqueurs HTML colorés par quartile de prix avec prix affiché directement sur la carte, liaison liste↔carte, popup, itinéraire via URI `geo:` (app de maps par défaut). Responsive mobile : bottom sheet 3 positions, bouton géoloc.
- **Belgique** : pas d'open data par station en Belgique. À proximité de la frontière (~20 km), un panneau affiche les prix maximum réglementés (Statbel) à côté des stations françaises frontalières (affichage hybride). La détection utilise un polygone qui suit la frontière, pas une bbox rectangulaire (pour exclure Arras, Cambrai, etc.).

## Endpoints API

| Endpoint | Description |
|---|---|
| `GET /health` | Statut, dernière mise à jour ETL, `stale` (seuil 26h) |
| `GET /api/fuels` | Liste des 6 carburants |
| `GET /api/stations/search` | Recherche par rayon (`lat`, `lon`, `radius_m`, `fuel`, `sort`, pagination) |
| `GET /api/stations/{id}` | Détail d'une station (tous carburants, services, horaires) |
| `GET /api/be/prices` | Prix maximum officiels Belgique (filtre optionnel `fuel`) |

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `POSTGRES_DB` | `fuelnow` | Nom de la base |
| `POSTGRES_USER` | `fuelnow` | Utilisateur DB |
| `POSTGRES_PASSWORD` | `changeme` | Mot de passe DB |
| `DATABASE_URL` | — | URL SQLAlchemy async (obligatoire, à construire manuellement) |
| `SOURCE_DATASET_URL` | URL par défaut | URL du dataset ODS (export JSON gzip) |
| `ETL_CRON` | `0 6 * * *` | Schedule cron ETL France (format 5 champs, supercronic ajoute les secondes) |
| `ETL_BE_CRON` | `0 7 * * *` | Schedule cron ETL Belgique |
| `STATBEL_API_URL` | URL par défaut | URL de l'API Statbel pour les prix maximum belges |
| `ETL_MIN_ROWS` | `5000` | Seuil minimum absolu de stations |
| `ETL_MIN_RATIO` | `0.8` | Ratio minimum vs dernier run réussi |
| `RATE_LIMIT_PER_MIN` | `60` | Requêtes/min/IP sur tous les endpoints |
| `SEARCH_RADIUS_MAX_M` | `30000` | Rayon max (mètres) |
| `CACHE_TTL_S` | `900` | TTL Cache-Control sur `/search` |
| `LOG_LEVEL` | `INFO` | Niveau de log |
| `CORS_ALLOW_ORIGINS` | (vide) | Origines CORS séparées par virgules (vide = désactivé) |
| `ALERT_WEBHOOK_URL` | (vide) | Webhook d'alerte (Discord/ntfy) si ETL échoue |
| `WEB_PORT` | `8080` | Port d'exposition du frontend nginx |

## Commandes utiles

```bash
# Tests
docker compose run --rm api pytest tests/ -q

# ETL manuel
docker compose run --rm etl python -m etl.run
docker compose run --rm etl python -m etl.be_run

# Logs ETL
docker compose logs -f etl

# Accéder à la DB
docker compose exec db psql -U fuelnow -d fuelnow
```

## Carburants supportés

Gazole · SP95 · SP98 · E10 · E85 · GPLc

## Source des données

[Prix des carburants en France – flux instantané v2](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/) — data.economie.gouv.fr / Opendatasoft. Cartes © OpenStreetMap contributors.

Prix maximum officiels Belgique : [Statbel/be.STAT](https://bestat.statbel.fgov.be/bestat/api/views/9e9cf394-6c54-4d81-8013-7124a8c4bf15/result/JSON).
