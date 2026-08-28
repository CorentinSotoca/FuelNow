# PROGRESS — FuelNow

## Où en est-on
- Étape courante : 0/10 — Bootstrap repo
- Statut : terminé
- Dernière vérif : `git log --oneline` affiche le commit initial

## À faire maintenant (prochaine action concrète)
1. Créer `docker-compose.yml` avec le service `db` (postgis/postgis:16-3.4) + volume `pgdata`.
2. Vérifier : `docker compose up -d db && docker compose exec db psql -U fuelnow -c "select postgis_version()"`
3. Attendu : PostGIS répond avec une version 3.x.

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
- [ ] 1 Docker db
- [ ] 2 Schéma DB + migrations
- [ ] 3 ETL fetch + parse
- [ ] 4 ETL chargement atomique
- [ ] 5 API search
- [ ] 6 Durcissement API
- [ ] 7 Frontend carte
- [ ] 8 Frontend résultats
- [ ] 9 Prod compose
- [ ] 10 Finitions

## Journal (3 dernières entrées)
- 2026-08-28 — étape 0 : git init, arbo `api/ web/ docs/ scripts/`, `.gitignore`, `.env.example`, `docs/ARCHITECTURE.md` copié depuis le plan.

## Points ouverts / blocages
- (aucun)
