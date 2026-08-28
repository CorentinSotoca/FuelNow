# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 3/10 — ETL fetch + parse
- Statut : à démarrer
- Dernière vérif : `alembic upgrade head` → migration 001 appliquée, `\d+ stations` montre l'index GiST + `\d+ station_prices` montre l'index partiel

## À faire maintenant (prochaine action concrète)
1. Créer `api/etl/models.py` (StationRecord Pydantic), `api/etl/adapters.py` (OdsJsonAdapter, dépivot 6 carburants).
2. Créer `api/tests/fixtures/ods_sample.json` (~20 stations avec cas limites).
3. Créer `api/tests/test_etl_parse.py`.
4. Vérifier : `docker compose run --rm api pytest api/tests/test_etl_parse.py -q`

## Contexte minimal indispensable
- Doc d'architecture : `docs/ARCHITECTURE.md` (à lire avant toute décision).
- Source données : dataset ODS `prix-des-carburants-en-france-flux-instantane-v2`
  sur data.economie.gouv.fr, export JSON **gzip**, modèle wide (1 col/carburant),
  ignorer `latitude`/`longitude` (entiers x100000) → utiliser `geom`.
- Stack figée : PostgreSQL+PostGIS / FastAPI async / React+Vite+MapLibre / Docker Compose.
- DB en cours : `docker compose up -d db`, migration 001 appliquée.

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
- `docker compose run --rm api pytest api/tests -q`

## Étapes
- [x] 0 Bootstrap repo
- [x] 1 Docker db
- [x] 2 Schéma DB + migrations
- [ ] 3 ETL fetch + parse    <-- ici
- [ ] 4 ETL chargement atomique
- [ ] 5 API search
- [ ] 6 Durcissement API
- [ ] 7 Frontend carte
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 2 : pyproject.toml, Dockerfile, alembic.ini/env.py, migration 001 (postgis, ENUMs, stations, station_prices, etl_runs, index GiST). psycopg2-binary ajouté pour le sync driver. `alembic upgrade head` OK.
- 2026-08-28 — étape 1 : docker-compose.yml avec db (postgis/postgis:16-3.4), volume pgdata, healthcheck. PostGIS 3.4 vérifié.
- 2026-08-28 — étape 0 : git init, arbo, .gitignore, .env.example, docs/ARCHITECTURE.md, PROGRESS.md.

## Points ouverts / blocages
- (aucun)
