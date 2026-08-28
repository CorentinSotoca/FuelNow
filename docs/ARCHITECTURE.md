# FuelNow — Architecture technique

Projet greenfield (`/home/corentin/perso/fuelnow` vide). Objectif : site web « stations les moins chères autour d'un point », carte OSM, données carburants rafraîchies quotidiennement, Docker sur VPS.

## 1. Source de données (vérifiée)

Le flux « v2 (améliorée) » référencé par data.gouv.fr est en réalité hébergé sur Opendatasoft :

| Élément | Valeur |
|---|---|
| Dataset ODS | `prix-des-carburants-en-france-flux-instantane-v2` sur `data.economie.gouv.fr` |
| Volume | ~9 800 enregistrements (1 ligne = 1 station) |
| Formats | CSV (`use_labels=true`), JSON, GeoJSON, SHP zip |
| Endpoint retenu | `.../api/explore/v2.1/catalog/datasets/<ds>/exports/json` |
| Réponse | gzip (à décompresser explicitement) |

Champs utiles confirmés : `id`, `adresse`, `cp`, `ville`, `pop` (R/A), `geom {lon,lat}`, `departement`, `code_departement`, `region`, puis par carburant : `gazole_prix|_maj`, `sp95_*`, `sp98_*`, `e10_*`, `e85_*`, `gplc_*`, plus `<fuel>_rupture_debut|_type` et `carburants_rupture_temporaire|definitive`. Colonnes `latitude`/`longitude` sont en entiers ×100000 → **ignorer, utiliser `geom`**.

Conséquence : modèle source « wide » (1 colonne par carburant) → l'ETL le **dépivote** en table longue `station_prices`.

## 2. Diagramme des composants

```
                    Internet
                       |
                 [ traefik / nginx ]  :80/:443  TLS
                    /            \
        /  (static)               \  /api/*
   [ web ]                        [ api ]
   nginx + SPA React/Vite         FastAPI (uvicorn)
   MapLibre GL + OSM raster            |
                                       | SQL (asyncpg)
                                       v
   [ etl ] --- pull HTTPS --->   [ db ] postgres:16 + PostGIS
   worker Python + cron 06:00          volume pgdata
        |                              |
        +--- upsert transactionnel ----+
```

Réseaux Docker : `edge` (proxy ↔ web/api), `backend` (api/etl ↔ db, non exposé).

## 3. Choix techno

| Couche | Choix | Raison |
|---|---|---|
| DB | PostgreSQL 16 + PostGIS 3 | `ST_DWithin` sur `geography` + index GiST = requête rayon native ; tri/filtre/distance en une seule requête SQL. Alternative SQLite+SpatiaLite écartée (ops concurrentes, migrations). |
| API | Python 3.12 + FastAPI + SQLAlchemy 2 (async) | Validation Pydantic des inputs géo, OpenAPI gratuit, même langage que l'ETL → un seul socle de dépendances. |
| ETL | Même image Python, entrypoint CLI (`python -m etl.run`) | Réutilise modèles/session SQLAlchemy, pas de duplication de schéma. |
| Scheduler | Conteneur `etl` avec cron (ou `supercronic`) `0 6 * * *` | Pas de dépendance externe, redémarrage géré par Docker `restart: unless-stopped`. Alternative : cron hôte appelant `docker compose run --rm etl`. |
| Frontend | React + Vite + TypeScript + MapLibre GL JS | Bundle statique servi par nginx, aucun runtime Node en prod ; MapLibre = perf sur milliers de marqueurs, style raster OSM ou vecteur. |
| Proxy | Traefik (ou nginx) | TLS Let's Encrypt auto, un seul point d'entrée, évite tout CORS (même origine). |

## 4. Schéma DB

```sql
CREATE EXTENSION postgis;

-- 1 ligne / station
stations(
  id            bigint PRIMARY KEY,          -- id source
  address       text,
  postal_code   text,
  city          text,
  dept_code     text, dept_name text, region_name text,
  road_type     text,                        -- pop: R=route, A=autoroute
  geom          geography(Point,4326) NOT NULL,
  services      jsonb,                       -- brut, non exploité v1
  opening_hours jsonb,                       -- brut, non exploité v1
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX stations_geom_gix ON stations USING GIST (geom);

-- 1 ligne / (station, carburant) : résultat du dépivot
station_prices(
  station_id   bigint REFERENCES stations(id) ON DELETE CASCADE,
  fuel         fuel_type NOT NULL,           -- ENUM: gazole,sp95,sp98,e10,e85,gplc
  price_eur    numeric(5,3),                 -- NULL si non vendu
  price_maj    timestamptz,
  outage       outage_type,                  -- ENUM: none,temporary,definitive
  PRIMARY KEY (station_id, fuel)
);
CREATE INDEX station_prices_fuel_price_idx
  ON station_prices (fuel, price_eur) WHERE price_eur IS NOT NULL;

-- métadonnées de run ETL (1 ligne / exécution, purge > 30j)
etl_runs(id serial pk, started_at, finished_at, status, rows_stations int,
         rows_prices int, source_bytes bigint, error text);
```

Pas d'historique : `station_prices` est intégralement remplacée à chaque run. Volumétrie : ~10k stations × ~6 carburants ≈ 60k lignes → **< 50 Mo** avec index. Impact disque négligeable ; prévoir 2 Go pour le volume pgdata (WAL + marge).

Purge : `DELETE FROM etl_runs WHERE started_at < now() - interval '30 days'` en fin de run. Pas de partitionnement ni de compaction nécessaires ; `VACUUM ANALYZE` post-swap (voir §5).

## 5. Flux ingestion (atomique)

1. **Fetch** : `GET .../exports/json`, en-têtes `If-None-Match` / `If-Modified-Since` persistés dans `etl_runs` (ou table `etl_state`). HTTP 304 → run marqué `skipped`, arrêt. Timeout 120 s, 3 retries backoff exponentiel. Décompression gzip.
2. **Parse** : adaptateur `SourceAdapter` (interface `iter_stations() -> Iterator[StationRecord]`) → une implémentation `OdsJsonAdapter`, une seconde possible `OdsCsvAdapter` en secours si l'export JSON change. Validation Pydantic ligne par ligne ; lignes invalides comptées, pas bloquantes.
3. **Normalisation** : dépivot des 6 carburants ; `price_eur` rejeté si hors [0.5, 5.0] ; `geom` rejeté si hors bbox France + DOM ; dédoublonnage sur `id`.
4. **Garde-fou qualité** : si `count(stations) < 80 %` du dernier run réussi, ou < 5000 → run `failed`, **aucune écriture**, données précédentes conservées.
5. **Chargement** : tables `stations_stg` / `station_prices_stg` (`TRUNCATE` + `COPY`), puis une seule transaction :
   `BEGIN; TRUNCATE station_prices, stations; INSERT INTO stations SELECT * FROM stations_stg; INSERT INTO station_prices SELECT * FROM station_prices_stg; COMMIT;`
   → jamais d'état partiel visible. (Le swap par `ALTER TABLE ... RENAME` est évité : casse les FK et les vues ; inutile à cette volumétrie.)
6. **Post** : `ANALYZE`, purge `etl_runs`, log JSON structuré, mise à jour `/health` de l'API via lecture de `etl_runs`.

Observabilité : logs JSON stdout (récupérés par `docker logs` / loki), `GET /health` renvoyant `last_success_at` + `age_hours`, et `stale=true` si > 30 h. Alerting minimal optionnel : appel webhook (Discord/ntfy) si run `failed`.

## 6. API

Base : `/api`. OpenAPI exposé en dev uniquement.

### `GET /api/stations/search`
Paramètres :

| Param | Type | Règle |
|---|---|---|
| `lat` | float | −90..90, requis |
| `lon` | float | −180..180, requis |
| `radius_m` | int | 500..30000, défaut 5000 |
| `fuel` | enum | `gazole|sp95|sp98|e10|e85|gplc`, requis |
| `include_unpriced` | bool | défaut `false` |
| `include_outage` | bool | défaut `false` (exclut rupture temporaire **et** définitive) |
| `sort` | enum | `price` (défaut) \| `distance` |
| `page` / `page_size` | int | 1.. / 1..100, défaut 25 |

Requête : `ST_DWithin(geom, ST_MakePoint(:lon,:lat)::geography, :radius_m)` + join `station_prices` sur `fuel`.
Tri : `price_eur ASC NULLS LAST, distance_m ASC` (tie-break distance). `sort=distance` → `distance_m ASC, price_eur ASC`.
Stations sans prix pour le carburant : **exclues par défaut** ; si `include_unpriced=true`, renvoyées avec `price_eur: null` en fin de liste.

Réponse (par item) : `id, name/address, city, postal_code, road_type, lat, lon, distance_m, price_eur, price_updated_at, outage, cheapest_delta_eur`.
Enveloppe : `{ items, total, page, page_size, data_updated_at, stale }`.

### Autres endpoints
- `GET /api/fuels` → liste des carburants + libellés (alimente le select).
- `GET /api/stations/{id}` → détail station (tous carburants, services, horaires bruts).
- `GET /health` → `{status, last_success_at, age_hours, stale}`.
- `GET /metrics` (optionnel, prometheus, restreint au réseau interne).

Règles transverses :
- Validation stricte Pydantic ; 422 sur param hors bornes, 503 si base jamais peuplée.
- Rate limit `slowapi` : 60 req/min/IP sur `/search` (clé = IP réelle via `X-Forwarded-For` du proxy).
- CORS : désactivé en prod (même origine via proxy) ; `localhost:5173` autorisé en dev.
- Cache : `Cache-Control: public, max-age=900` + `ETag` sur `/search` ; optionnellement cache applicatif in-process (LRU 500 entrées, TTL 15 min) clé = `(lat,lon arrondis 3 déc., radius, fuel, sort, page)`. Redis non nécessaire à cette échelle.
- Pas d'auth (données publiques, service en lecture seule).

## 7. Frontend / UX

Parcours : carte plein écran + panneau latéral (bottom sheet en mobile).

1. Géolocalisation navigateur proposée au chargement (fallback centre France, zoom 6).
2. **Sélection du point** : clic sur la carte ou marqueur draggable ; champ de recherche d'adresse optionnel (Nominatim, usage modéré + attribution).
3. **Rayon** : slider 0,5 → 30 km, cercle `GeoJSON` affiché en live sur la carte.
4. **Carburant** : segmented control alimenté par `/api/fuels`.
5. Recherche déclenchée en debounce 400 ms (ou bouton explicite si `radius` large).
6. **Liste triée** : rang, prix en gros, écart vs le moins cher, distance, adresse/ville, badge autoroute, « MAJ il y a Xh », lien itinéraire (`https://www.openstreetmap.org/directions?...` ou geo: URI mobile).
7. Interaction croisée : hover/clic liste ↔ marqueur (marqueur coloré par quartile de prix), popup au clic.

Composants : `MapView`, `RadiusControl`, `FuelSelect`, `ResultsList`, `StationCard`, `StatusBanner`.
États d'erreur : aucun résultat (« élargir le rayon » + bouton +5 km), erreur réseau (retry), `stale=true` → bandeau « données du JJ/MM, mise à jour en retard », 429 → message d'attente.
Accessibilité/perf : liste virtualisée si > 200 items, clustering au-delà de 500 marqueurs, attribution OSM obligatoire.

## 8. Docker & ops

Services :

| Service | Image / build | Rôle | Exposé |
|---|---|---|---|
| `db` | `postgis/postgis:16-3.4` | données | non (réseau `backend`) |
| `api` | build `./api` (multi-stage python:3.12-slim, venv + uv) | FastAPI/uvicorn | via proxy |
| `etl` | même image que `api`, command = supercronic | pull 06:00 | non |
| `web` | build `./web` (stage node:22 build → nginx:alpine) | SPA statique | via proxy |
| `proxy` | `traefik:v3` | TLS + routage | 80/443 |

Snippet minimal (illustratif) :

```yaml
services:
  db:
    image: postgis/postgis:16-3.4
    environment: [POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"]
      interval: 10s
    networks: [backend]
  api:
    build: ./api
    env_file: .env
    depends_on: { db: { condition: service_healthy } }
    healthcheck: { test: ["CMD", "curl", "-fs", "http://localhost:8000/health"] }
    networks: [backend, edge]
  etl:
    build: ./api
    command: ["supercronic", "/etc/crontab"]   # 0 6 * * * python -m etl.run
    env_file: .env
    depends_on: { db: { condition: service_healthy } }
    networks: [backend]
volumes: { pgdata: {} }
networks: { backend: { internal: true }, edge: {} }
```

Variables d'environnement (`.env`, jamais commité ; `.env.example` versionné) :
`POSTGRES_DB/USER/PASSWORD`, `DATABASE_URL`, `TZ=Europe/Paris`, `SOURCE_DATASET_URL`, `SOURCE_FORMAT=json`, `ETL_CRON=0 6 * * *`, `ETL_MIN_ROWS=5000`, `RATE_LIMIT_PER_MIN=60`, `SEARCH_RADIUS_MAX_M=30000`, `CACHE_TTL_S=900`, `LOG_LEVEL`, `ALERT_WEBHOOK_URL` (optionnel), `PUBLIC_HOSTNAME`, `ACME_EMAIL`.

Commandes :
- `docker compose up -d --build`
- `docker compose run --rm etl python -m etl.run` (premier remplissage / rejeu manuel)
- `docker compose exec api alembic upgrade head` (migrations, aussi lancées au démarrage via entrypoint)
- `docker compose logs -f etl`

VPS cible : **2 vCPU / 2 Go RAM / 20 Go SSD** suffisent largement (Postgres ~512 Mo, api ~200 Mo, pic ETL ~300 Mo). `shared_buffers=256MB`. Sauvegarde : non critique (données reconstructibles en un run) → un `pg_dump` hebdo optionnel. `TZ=Europe/Paris` sur `etl` pour que 06:00 soit local.

## 9. Qualité

- **Tests ETL (unitaires)** : fixtures JSON réelles tronquées (~20 stations, dont prix manquants, rupture définitive, `geom` aberrant) → assertions sur dépivot, rejets, garde-fou seuil.
- **Tests API (intégration)** : `pytest` + `testcontainers` ou service `db` de CI ; jeu de 5 stations connues → vérifier rayon, tri prix, tie-break distance, exclusion rupture, bornes 422, pagination.
- **Smoke test post-déploiement** : `/health` non stale + `/api/stations/search?lat=48.85&lon=2.35&radius_m=3000&fuel=gazole` renvoie ≥ 1 item avec prix croissants.
- **Frontend** : tests composants légers (Vitest) sur formatage prix/distance ; un test e2e Playwright du parcours nominal.
- **Migrations** : Alembic, `postgis` créé dans la première révision ; migrations idempotentes appliquées à l'entrypoint api.
- **Secrets** : uniquement variables d'env / `.env` à `chmod 600` sur le VPS ; aucun secret dans l'image ; pas de secret réel dans le repo.
- **CI** : lint (ruff, eslint), tests, build des images.

## 10. Risques & mitigations

| Risque | Mitigation |
|---|---|
| Source indisponible / schéma modifié | Retries + validation Pydantic + garde-fou 80 % → dernier état conservé, bandeau `stale` en UI, alerte webhook. |
| Export ODS remplacé (URL/format) | Adaptateur pluggable (`SOURCE_FORMAT`), fallback CSV, URL en variable d'env. |
| Prix aberrants dans la source | Bornes [0,5–5,0 €] + rejet log. |
| Requête rayon 30 km en zone dense | Index GiST + `page_size` max 100 + cache 15 min ; volumétrie 10k = qq ms. |
| Abus / scraping de l'API | Rate limit, `page_size` borné, pas d'endpoint « toute la France ». |
| Coordonnées `latitude/longitude` ×100000 mal interprétées | Utiliser exclusivement `geom` ; test unitaire sur bbox France. |
| Cron manqué (VPS éteint/reboot) | Détection `stale` au démarrage de l'ETL → run de rattrapage immédiat si `age > 26 h`. |
| Confusion timezone sur `*_maj` | Tout stocké en `timestamptz` UTC, formaté côté client. |

## 11. Évolutions prévues

- **Historique** : ajouter `price_history(station_id, fuel, price_eur, observed_at)` partitionnée par mois, alimentée en fin d'ETL par diff avec l'état courant (l'architecture actuelle n'a rien à jeter : le remplacement devient « diff puis remplace »).
- Isochrones (temps de trajet) au lieu du cercle, via OSRM/Valhalla.
- Alertes utilisateur par email/push sur seuil de prix (nécessite comptes → Redis/queue).
- Scalabilité : réplica lecture + Redis pour le cache si trafic > quelques req/s ; sinon aucun changement requis.

## 12. Plan d'exécution par étapes

Règle absolue : **une étape = un commit + une mise à jour de `PROGRESS.md`**. Ne jamais démarrer l'étape N+1 avant que l'étape N soit vérifiée et cochée.

| # | Étape | Livrable | Vérification (commande) |
|---|---|---|---|
| 0 | Bootstrap repo | `git init`, arbo `api/ web/ docs/`, `.gitignore`, `.env.example`, `PROGRESS.md` | `ls` + `git log --oneline` |
| 1 | Docker db + compose squelette | `docker-compose.yml` avec `db` seul, volume `pgdata` | `docker compose up -d db && docker compose exec db psql -U $POSTGRES_USER -c "select postgis_version()"` |
| 2 | Schéma DB + migrations | Alembic rév. 1 (extension postgis, ENUMs, `stations`, `station_prices`, `etl_runs`, index GiST) | `alembic upgrade head` puis `\d+ stations` montre l'index GiST |
| 3 | ETL fetch + parse | `api/etl/` : `OdsJsonAdapter`, modèles Pydantic, dépivot des 6 carburants | `pytest api/tests/test_etl_parse.py` sur fixture ~20 stations |
| 4 | ETL chargement atomique | staging + `TRUNCATE`+`INSERT` en une transaction, garde-fou `ETL_MIN_ROWS`/80 %, `etl_runs` | `docker compose run --rm etl python -m etl.run` → `select count(*) from stations` ≈ 9800 |
| 5 | API search | FastAPI `/health`, `/api/fuels`, `/api/stations/search` (rayon, tri, pagination, 422) | `curl "localhost:8000/api/stations/search?lat=48.85&lon=2.35&radius_m=3000&fuel=gazole"` → prix croissants |
| 6 | Durcissement API | rate limit, ETag/Cache-Control, flag `stale`, logs JSON | `pytest api/tests/test_api_search.py` (bornes, tri, exclusion rupture) |
| 7 | Frontend carte | Vite + React + MapLibre : carte, point cliquable, cercle rayon, select carburant | `npm run dev` → carte OSM affichée, cercle réactif au slider |
| 8 | Frontend résultats | `ResultsList`, liaison liste↔marqueurs, états vide/erreur/`stale` | recherche Paris gazole → liste triée cohérente avec `curl` |
| 9 | Prod compose | services `api`/`etl`/`web`/`proxy`, healthchecks, réseaux `edge`/`backend`, cron 06:00 | `docker compose up -d --build` puis `curl -f https://$PUBLIC_HOSTNAME/health` |
| 10 | Finitions | README déploiement, smoke test scripté, purge `etl_runs`, alerte webhook optionnelle | `./scripts/smoke.sh` vert |

Ordre imposé par les dépendances : 0 → 1 → 2 → 3 → 4 → 5 → 6, et 7 → 8 peuvent démarrer dès l'étape 5 terminée (API contractuelle disponible). 9 exige 6 et 8.

## 13. Suivi d'avancement (`PROGRESS.md`)

Créer `PROGRESS.md` à la racine **dès l'étape 0** et le mettre à jour **à la fin de chaque étape**. C'est le point d'entrée unique pour reprendre le travail : il doit être auto-suffisant pour un agent qui n'a aucun contexte de conversation.

Contraintes de rédaction :
- Toujours en français, < 120 lignes, réécrit et non empilé indéfiniment (garder au maximum les 3 dernières entrées de journal détaillées).
- Toujours indiquer : l'étape courante, l'étape suivante, **la commande exacte** pour vérifier l'état, et les décisions déjà figées à ne pas rediscuter.
- Ne jamais y stocker de secret (valeurs de `.env`).

Gabarit :

```markdown
# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 4/10 — ETL chargement atomique
- Statut : en cours (staging OK, transaction de swap à écrire)
- Dernière vérif réussie : `pytest api/tests/test_etl_parse.py` (20 passed)

## À faire maintenant (prochaine action concrète)
1. Écrire `api/etl/load.py` : TRUNCATE + INSERT dans une seule transaction.
2. Vérifier : `docker compose run --rm etl python -m etl.run`
3. Attendu : `select count(*) from stations` ≈ 9800, ligne `status=success` dans `etl_runs`.

## Contexte minimal indispensable
- Doc d'architecture : `docs/ARCHITECTURE.md` (à lire avant toute décision).
- Source données : dataset ODS `prix-des-carburants-en-france-flux-instantane-v2`
  sur data.economie.gouv.fr, export JSON **gzip**, modèle wide (1 col/carburant),
  ignorer `latitude`/`longitude` (entiers x100000) → utiliser `geom`.
- Stack figée : PostgreSQL+PostGIS / FastAPI async / React+Vite+MapLibre / Docker Compose.

## Décisions figées (ne pas rediscuter)
- Pas d'historique de prix en v1.
- Stations sans prix exclues par défaut ; ruptures temporaires et définitives exclues.
- Remplacement complet des données à chaque run, en une transaction.

## Commandes utiles
- `docker compose up -d db && docker compose exec api alembic upgrade head`
- `docker compose run --rm etl python -m etl.run`
- `pytest api/tests -q`

## Étapes
- [x] 0 Bootstrap repo
- [x] 1 Docker db
- [x] 2 Schéma DB + migrations
- [x] 3 ETL fetch + parse
- [ ] 4 ETL chargement atomique   <-- ici
- [ ] 5 API search
- [ ] 6 Durcissement API
- [ ] 7 Frontend carte
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 3 : adaptateur JSON + dépivot, 20 tests verts. Fixture dans `api/tests/fixtures/ods_sample.json`.
- ...

## Points ouverts / blocages
- (aucun)
```

Copier également la présente doc d'architecture dans `docs/ARCHITECTURE.md` à l'étape 0, afin que le repo soit autonome sans le fichier de plan.

## 14. Hypothèses

1. La ressource « améliorée » visée est bien le dataset ODS `prix-des-carburants-en-france-flux-instantane-v2` (data.economie.gouv.fr), pas le ZIP/XML `roulez-eco.fr` historique.
2. Le pull unique à 06:00 (heure Paris) est suffisant ; pas de besoin temps réel intra-journalier.
3. Aucun compte utilisateur, aucune donnée personnelle stockée (pas de contrainte RGPD au-delà des logs IP, purgés à 7 j).
4. Périmètre France métropolitaine + DOM tel que fourni par la source, pas de filtrage géographique métier.
5. 6 carburants figés (gazole, sp95, sp98, e10, e85, gplc) ; un nouveau carburant nécessite une migration d'ENUM.
6. Ruptures temporaires **et** définitives exclues par défaut des résultats ; horaires et services stockés bruts mais non exploités en v1.
7. Un seul VPS, pas de HA, downtime de déploiement acceptable.
8. L'utilisateur gère domaine, DNS et déploiement ; Traefik est une recommandation, un nginx existant peut le remplacer.
9. Le repo suivra la structure `api/` (FastAPI + `etl/`), `web/` (SPA), `docker-compose.yml`, `.env.example`, `docs/`.
