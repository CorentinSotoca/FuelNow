# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 2/10 — Schéma DB + migrations
- Statut : à démarrer
- Dernière vérif : `docker compose exec db psql -U fuelnow -c "select postgis_version()"` → PostGIS 3.4 OK

## À faire maintenant (prochaine action concrète)
1. Créer `api/pyproject.toml` (dépendances : fastapi, uvicorn, sqlalchemy, asyncpg, alembic, pydantic, httpx, geoalchemy2).
2. Créer `api/alembic.ini` + `api/alembic/env.py` + première révision (extension postgis, ENUMs, `stations`, `station_prices`, `etl_runs`, index GiST).
3. Vérifier : `docker compose exec api alembic upgrade head` puis `\d+ stations` montre l'index GiST.

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
- 6 carburants : gazole, sp95, sp98, e10, e85, gplc.
- Prix bornés [0.5, 5.0] € ; geom hors bbox France rejeté.

## Commandes utiles
- `docker compose up -d db && docker compose exec api alembic upgrade head`
- `docker compose run --rm etl python -m etl.run`
- `pytest api/tests -q`

## Étapes
- [x] 0 Bootstrap repo
- [x] 1 Docker db
- [ ] 2 Schéma DB + migrations    <-- ici
- [ ] 3 ETL fetch + parse
- [ ] 4 ETL chargement atomique
- [ ] 5 API search
- [ ] 6 Durcissement API
- [ ] 7 Frontend carte
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 1 : docker-compose.yml avec db (postgis/postgis:16-3.4), volume pgdata, healthcheck. PostGIS 3.4 vérifié.
- 2026-08-28 — étape 0 : git init, arbo, .gitignore, .env.example, docs/ARCHITECTURE.md, PROGRESS.md.

## Points ouverts / blocages
- (aucun)
