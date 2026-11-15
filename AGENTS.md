# AGENTS.md — FuelNow

## Vue d'ensemble

FuelNow est une application web dockerisée qui permet de trouver les stations-service les moins chères autour d'un point donné. Données carburants rafraîchies quotidiennement depuis le flux officiel **Prix des carburants en France – flux instantané v2** (data.economie.gouv.fr / Opendatasoft). En zone belge, affichage des prix maximum réglementés depuis **Statbel/be.STAT**.

## Stack

| Couche | Techno |
|---|---|
| Base de données | PostgreSQL 16 + PostGIS 3.4 |
| API | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · asyncpg |
| MCP | Model Context Protocol (spec 2025-11-25) · `mcp` SDK v2 · Streamable HTTP |
| ETL | Python · httpx · SQLAlchemy Core · supercronic (cron FR 06:00, BE 07:00) |
| Frontend | React 19 · TypeScript · Vite 8 · MapLibre GL JS v6 |
| Prod | Docker Compose · nginx (SPA + reverse proxy) |

## Structure du repo

```
api/                  FastAPI + ETL (même image Python)
  app/                Application FastAPI
    routes/           health, fuels, stations, be
    services.py       Couche service (logique DB partagée entre routes et MCP)
    mcp_server.py     Serveur MCP (MCPServer, 5 tools, Streamable HTTP)
    config.py         Settings (env vars)
    db.py             Engine SQLAlchemy async
    limiter.py        Rate limit slowapi
    schemas.py        Pydantic models
    status.py         last_success_at / stale (seuil 26h, filtré par source='fr')
  etl/                Pipeline ETL
    adapters.py       OdsJsonAdapter (fetch + dépivot)
    be_adapter.py     StatbelAdapter (fetch + parse prix max BE)
    osm.py            OverpassAdapter (fetch Overpass + parse POIs OSM → enseignes)
    models.py         StationRecord, StationPriceRecord, Fuel, Outage
    load.py           staging tables + TRUNCATE/INSERT atomique + rebuild enseignes
    runs.py           Shared helpers (create_run, update_run, send_alert, cleanup_orphaned_runs)
    run.py            Orchestrateur FR + etl_runs (source='fr') + enseignes OSM
    be_run.py         Orchestrateur BE + etl_runs (source='be')
    entrypoint.sh     supercronic (-no-reap, génère crontab au runtime, 2 entries FR+BE)
  tests/              Tests (13 ETL parse + 12 API search + 10 BE adapter + 5 BE API + 7 ETL load + 10 OSM adapter + 2 OSM load)
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
| `POST /mcp` | Serveur MCP (Streamable HTTP, tools/list, tools/call, initialize) |
| `GET /.well-known/mcp-server` | Manifest de découverte MCP (endpoint, transport, capabilities) |

## Serveur MCP

FuelNow expose un serveur MCP public (sans auth) sur `https://fuelnow.squale.ovh/mcp` via le transport Streamable HTTP (spec 2025-11-25).

- **SDK** : `mcp` v2 (`MCPServer` de `mcp.server.mcpserver`).
- **Montage** : `app.mount("/", mcp.streamable_http_app())` — l'app MCP a sa propre route interne `/mcp`, d'où le mount à la racine.
- **Lifespan** : le `session_manager.run()` doit être lancé dans le lifespan de l'app hôte FastAPI, sinon `RuntimeError: Task group is not initialized`.
- **DNS rebinding protection** : désactivée (`TransportSecuritySettings(enable_dns_rebinding_protection=False)`) car nginx est le front-facing server.
- **Well-known** : `/.well-known/mcp-server` sert un manifest JSON (endpoint, transport, protocolVersion, capabilities).
- **Nginx** : `location /mcp` avec `proxy_buffering off` (SSE streaming), `proxy_read_timeout 86400s`.

### 5 tools exposés

| Tool | Description |
|---|---|
| `search_stations` | Recherche par geo + fuel + rayon (mêmes params que l'API REST) |
| `get_station_detail` | Détail d'une station (adresse, prix, services, horaires) |
| `list_fuels` | 6 carburants disponibles |
| `get_be_prices` | Prix maximum réglementés Belgique |
| `get_health` | Statut API + fraîcheur des données |

La logique métier est dans `api/app/services.py`, partagée entre les route handlers FastAPI et les tools MCP (pas de duplication de SQL).

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
- Enseignes : issues d'OpenStreetMap (Overpass `amenity=fuel`), match exact par tag `ref:FR:prix-carburants` (même id que le flux officiel), sinon POI le plus proche à < 150 m. Cache `osm_fuel_pois` rafraîchi hebdomadairement (non fatal), `station_brands` reconstruite à chaque run FR dans la même transaction que le swap des stations.
- Waze/Google Maps ciblent le POI de l'enseigne (requête texte « enseigne, adresse, cp ville »), pas un pin sur l'adresse brute. Sans enseigne : retombée sur les coordonnées.
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

### Enseignes OSM (Overpass)

- Overpass rate-limit (429) fréquemment : `OverpassAdapter.fetch` retente 3 fois par endpoint avec backoff, puis bascule sur l'endpoint suivant (`OVERPASS_URLS`, endpoints séparés par virgules).
- Le refresh OSM est **non fatal** : en cas d'échec, l'ancien cache est conservé — les nouvelles stations restent sans enseigne jusqu'au prochain refresh. Un POI sans `brand` ni `name` est ignoré (rien à afficher).
- Le tag `ref:FR:prix-carburants` peut contenir plusieurs ids séparés par `;` → un enregistrement par id dans `osm_fuel_pois` (la jointure exacte est un simple `station_ref = s.id`).
- `station_brands` a une FK vers `stations` : le `TRUNCATE` de `load_stations_atomically` doit lister les trois tables (`station_brands, station_prices, stations`), sinon Postgres refuse de tronquer `stations`.
- Le rebuild des enseignes tourne dans la MÊME transaction que le remplacement des stations → l'API ne voit jamais `station_brands` vide.

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
- **Boutons Waze/Maps** : construits par `stationNavLinks()` dans `utils.ts` — Google Maps reçoit une requête texte « enseigne, adresse, cp ville » (ouvre la fiche de l'établissement), Waze reçoit `q=enseigne ville` + `ll=lat,lon` + `navigate=yes` (résout le POI nommé). Sans enseigne : retombée sur les coordonnées seules. L'ancien URI `geo:` / Apple Maps a été retiré. `target="_blank" rel="noopener noreferrer"` + `stopPropagation` (le clic ne sélectionne pas la carte).
- **Popup station** : affiche prix, adresse, code postal + ville, distance.
- **Marqueurs HTML MapLibre** : ne **pas** mettre `transform: translate(-50%,-50%)` dans le style de l'élément — MapLibre gère lui-même le positionnement. Ne **pas** utiliser `replaceWith` pour mettre à jour un marker — appliquer les styles in-place sur `marker.getElement()` via `applyStationElStyle`.
- **TypeScript** : `erasableSyntaxOnly: false` dans `tsconfig.app.json` (bloque les classes avec param properties comme ApiError).
- Classes CSS popup en maplibre-gl v6 : préfixées `maplibregl-` (pas `maplibre-`).
- **Zone belge** : `isNearBelgium(lat, lon)` dans `utils.ts` utilise un polygone (algorithme du ray-casting) qui suit la frontière franco-belge + ~20 km de tampon côté français. Une bbox rectangulaire ne fonctionne pas car elle inclurait des villes françaises éloignées de la frontière (Arras, Cambrai, Béthune, Lens, Douai). Le polygone exclut ces villes tout en incluant Lille, Valenciennes, Maubeuge, Dunkerque, Hirson, Givet. Quand `isNearBelgium` est vrai, le hook `useDebouncedSearch` fetch les prix BE via `GET /api/be/prices` et `BeMaxPricePanel` s'affiche en haut des résultats. Les stations FR frontalières restent visibles (affichage hybride).
- **CSP & MapLibre** : la CSP a été retirée de `nginx.conf` car elle bloquait les tuiles OSM. MapLibre v6 charge les tuiles via `fetch()` (donc `connect-src`, pas `img-src`), crée des blob URLs pour les images (`img-src blob:`) et précharge le worker via blob (`worker-src blob:`). De plus, `https://*.tile.openstreetmap.org` ne matche pas `https://tile.openstreetmap.org` (le wildcard `*.` exige un sous-domaine). Si la CSP est réimplémentée, il faut : `connect-src 'self' https://tile.openstreetmap.org https://*.tile.openstreetmap.org ; img-src 'self' https://tile.openstreetmap.org https://*.tile.openstreetmap.org data: blob: ; worker-src 'self' blob:`.
- **Permissions-Policy geolocation** : le nginx hôte (squale.ovh) bloquait la géoloc via `geolocation=()` dans le snippet partagé `/etc/nginx/snippets/security-headers.conf` — corrigé en `geolocation=(self)` le 2026-11-15. La géoloc nécessite toujours HTTPS (déjà le cas).

### Supercronic (ETL)

1. Format crontab = **5 champs standard** (min hour dom month dow). supercronic v0.2.33 supporte nativement ce format. Ne **pas** préfixer avec des secondes — le format 6 champs de supercronic est `min hour dom month dow sec` (secondes suffixées), pas `sec min hour dom month dow`. Préfixer "0 " décale tous les champs et transforme `0 6 * * *` (06h00 quotidien) en `0 0 6 * * *` (le 6 du mois à minuit).
2. supercronic en PID 1 crash sur "Failed to fork exec" → flag **`-no-reap`**.
3. Pas de substitution de variables d'env dans le crontab → `entrypoint.sh` génère le fichier au runtime.
4. Deux entries : FR (`etl.run`) et BE (`etl.be_run`).

### MCP

- **Mount à la racine** : l'app MCP définit sa propre route `/mcp` en interne. Si on mount sur `/mcp` au lieu de `/`, la route devient `/mcp/mcp` → 404.
- **Lifespan obligatoire** : `mcp.session_manager` n'existe qu'après `streamable_http_app()`. Le lifespan de l'app hôte doit entrer `session_manager.run()`, sinon chaque requête MCP → 500.
- **DNS rebinding** : le SDK active `enable_dns_rebinding_protection=True` par défaut avec `allowed_hosts=["127.0.0.1:*", "localhost:*"]`. En prod derrière nginx, le Host header est `fuelnow.squale.ovh` → 421. Désactivé via `TransportSecuritySettings`.
- **CORS** : le MCP utilise POST/DELETE (Streamable HTTP), pas seulement GET. Le CORS de l'app hôte doit autoriser ces méthodes.
- **Pas de rate limit sur /mcp** : slowapi agit via décorateur `@limiter.limit()` sur les routes, pas sur les mounts. `/mcp` n'est pas décoré → non limité.
- **Nginx buffering** : si `proxy_buffering` reste `on`, les SSE streams sont bufferisés → timeout MCP. `proxy_buffering off` obligatoire sur `location /mcp`.

### Responsive mobile

- Bottom sheet 3 positions : `collapsed` / `half` / `full` (handle cliquable pour cycler).
- Résumé peek en mode replié : nb stations + prix min (ou prix max BE si en zone belge).
- Bouton géoloc 📍 pour se positionner sans cliquer sur la carte.
- `@media (max-width: 768px)` dans `App.css`.

## Source des données

[Prix des carburants en France – flux instantané v2](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/) — data.economie.gouv.fr / Opendatasoft. Cartes © OpenStreetMap contributors.

Prix maximum officiels Belgique : [Statbel/be.STAT](https://bestat.economie.fgov.be/bestat/api/views/9e9cf394-6c54-4d81-8013-7124a8c4bf15/result/JSON).
