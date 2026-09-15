#!/bin/sh
set -e

CRON="${ETL_CRON:-0 6 * * *}"
BE_CRON="${ETL_BE_CRON:-0 7 * * *}"
echo "PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" > /tmp/crontab
# supercronic v0.2.33 supporte le format cron standard 5 champs (min hour dom month dow).
# Ne PAS préfixer "0" (secondes) — le format 6 champs de supercronic est min hour dom month dow sec
# (secondes suffixées), pas sec min hour dom month dow.
echo "${CRON} python -m etl.run" >> /tmp/crontab
echo "${BE_CRON} python -m etl.be_run" >> /tmp/crontab

exec supercronic -no-reap /tmp/crontab
