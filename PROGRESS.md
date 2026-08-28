# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 4/10 — ETL chargement atomique
- Statut : à démarrer
- Dernière vérif : `docker compose run --rm api pytest tests/test_etl_parse.py -q` → 13 passed

## À faire maintenant (prochaine action concrète)
1. Créer `api/etl/load.py` : staging tables + TRUNCATE+INSERT dans une seule transaction, garde-fou `ETL_MIN_ROWS`/80 %.
2. Créer `api/etl/run.py` : orchestre fetch → parse → garde-fou → load → etl_runs.
3. Vérifier : `docker compose run --rm etl python -m etl.run` → `select count(*) from stations` ≈ 9800.

## Contexte minimal indispensable
- Doc d'architecture : `docs/ARCHITECTURE.md` (à lire avant toute décision).
- Source données : dataset ODS `prix-des-carburants-en-france-flux-instantane-v2`
  sur data.economie.gouv.fr, export JSON **gzip**, modèle wide (1 col/carburant),
  ignorer `latitude`/`longitude` (entiers x100000) → utiliser `geom`.
- Stack figée : PostgreSQL+PostGIS / FastAPI async / React+Vite+MapLibre / Docker Compose.
- DB : docker compose up -d db, migration 001 appliquée.
- ETL parse : `api/etl/models.py` (StationRecord, StationPriceRecord, Fuel, Outage), `api/etl/adapters.py` (OdsJsonAdapter avec fetch async + dépivot). 13 tests verts.

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
- [ ] 4 ETL chargement atomique    <-- ici
- [ ] 5 API search
- [ ] 6 Durcissement API
- [ ] 7 Frontend carte
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 3 : etl/models.py (Pydantic StationRecord + StationPriceRecord, validation lat/lon/prix), etl/adapters.py (OdsJsonAdapter : fetch async gzip, dépivot 6 carburants, rupture temp/def). Fixture ods_sample.json (8 cas). 13 tests verts.
- 2026-08-28 — étape 2 : pyproject.toml, Dockerfile, alembic, migration 001. psycopg2-binary ajouté. `alembic upgrade head` OK.
- 2026-08-28 — étape 1 : docker-compose.yml avec db postgis. PostGIS 3.4 vérifié.

## Points ouverts / blocages
- (aucun)
