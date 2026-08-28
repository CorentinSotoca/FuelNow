# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 5/10 — API search
- Statut : à démarrer
- Dernière vérif : `docker compose run --rm etl python -m etl.run` → 9785 stations, 55121 prix chargés, `etl_runs` status=success.

## À faire maintenant (prochaine action concrète)
1. Implémenter `app/routes/stations.py` : `GET /api/stations/search` (lat, lon, radius_m, fuel, include_unpriced, include_outage, sort, page, page_size) avec requête PostGIS `ST_DWithin`.
2. Implémenter `GET /api/fuels`, `GET /api/stations/{id}`.
3. Vérifier via `docker compose up -d api` puis `curl` sur les endpoints.

## Contexte minimal indispensable
- Doc d'architecture : `docs/ARCHITECTURE.md` (à lire avant toute décision).
- Source données : dataset ODS `prix-des-carburants-en-france-flux-instantane-v2`
  sur data.economie.gouv.fr, export JSON **gzip**, modèle wide (1 col/carburant),
  ignorer `latitude`/`longitude` (entiers x100000) → utiliser `geom`.
- Stack figée : PostgreSQL+PostGIS / FastAPI async / React+Vite+MapLibre / Docker Compose.
- DB : docker compose up -d db, migration 001 appliquée.
- ETL parse : `api/etl/models.py` (StationRecord, StationPriceRecord, Fuel, Outage), `api/etl/adapters.py` (OdsJsonAdapter avec fetch async + dépivot). 13 tests verts.
- ETL load : `api/etl/load.py` (staging tables temp + inserts SQLAlchemy Core paramétrés par batch de 500 + TRUNCATE/INSERT en transaction), `api/etl/run.py` (orchestrateur + etl_runs). Point d'attention : ne jamais construire de SQL par interpolation de chaînes (problèmes de quoting JSON) — toujours passer par des paramètres liés ; ne jamais passer `func.now()`/expressions SQL dans des params `executemany` (asyncpg attend une vraie valeur Python) → utiliser `datetime.now(timezone.utc)`.

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
- [ ] 5 API search    <-- ici
- [ ] 6 Durcissement API
- [ ] 7 Frontend carte
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 4 : etl/load.py (staging tables temp + inserts SQLAlchemy Core par batch, TRUNCATE+INSERT en une transaction), etl/run.py (orchestrateur, etl_runs, garde-fou, alerte webhook optionnelle). Run réel OK : 9785 stations, 55121 prix.
- 2026-08-28 — étape 3 : etl/models.py (Pydantic StationRecord + StationPriceRecord, validation lat/lon/prix), etl/adapters.py (OdsJsonAdapter : fetch async gzip, dépivot 6 carburants, rupture temp/def). Fixture ods_sample.json (8 cas). 13 tests verts.
- 2026-08-28 — étape 2 : pyproject.toml, Dockerfile, alembic, migration 001. psycopg2-binary ajouté. `alembic upgrade head` OK.

## Points ouverts / blocages
- (aucun)
