#!/bin/sh
set -e

CRON="${ETL_CRON:-0 6 * * *}"
BE_CRON="${ETL_BE_CRON:-0 7 * * *}"
echo "PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" > /tmp/crontab
# supercronic attend 6 champs (sec min hour day month dow) ; si ETL_CRON en a 5,
# on préfixe avec "0" (0 secondes).

# FR ETL
FIELD_COUNT=$(echo "$CRON" | wc -w)
if [ "$FIELD_COUNT" -eq 5 ]; then
  echo "0 ${CRON} python -m etl.run" >> /tmp/crontab
else
  echo "${CRON} python -m etl.run" >> /tmp/crontab
fi

# BE ETL (prix maximum Statbel)
BE_FIELD_COUNT=$(echo "$BE_CRON" | wc -w)
if [ "$BE_FIELD_COUNT" -eq 5 ]; then
  echo "0 ${BE_CRON} python -m etl.be_run" >> /tmp/crontab
else
  echo "${BE_CRON} python -m etl.be_run" >> /tmp/crontab
fi

exec supercronic -no-reap /tmp/crontab
