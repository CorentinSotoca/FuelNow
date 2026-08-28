#!/bin/sh
set -e

CRON="${ETL_CRON:-0 6 * * *}"
echo "PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" > /tmp/crontab
# supercronic attend 6 champs (sec min hour day month dow) ; si ETL_CRON en a 5,
# on préfixe avec "0" (0 secondes).
FIELD_COUNT=$(echo "$CRON" | wc -w)
if [ "$FIELD_COUNT" -eq 5 ]; then
  echo "0 ${CRON} python -m etl.run" >> /tmp/crontab
else
  echo "${CRON} python -m etl.run" >> /tmp/crontab
fi
exec supercronic -no-reap /tmp/crontab
