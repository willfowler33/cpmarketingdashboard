#!/bin/bash
# Wait for the running backfill to finish, then re-discover (picks up Fortress + Artisan)
# and backfill their 30 days + stories.
cd /opt/ads-visibility
while pgrep -f backfill30.py >/dev/null; do sleep 15; done
set -a; . ./.env; set +a
./venv/bin/python discover.py > discover2.log 2>&1
./venv/bin/python backfill30.py > backfill_new.log 2>&1
echo "NEW ACCOUNTS DONE" >> backfill_new.log
