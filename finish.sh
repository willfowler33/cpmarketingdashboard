#!/bin/bash
# Wait for any running backfill to finish, then regenerate all stories.
cd /opt/ads-visibility
while pgrep -f backfill.sh >/dev/null; do sleep 10; done
set -a; . ./.env; set +a
DATE="$(date -d '-1 day' +%F)"
./venv/bin/python - "$DATE" <<'PY'
import sys, db, summarize
con = db.connect(); date = sys.argv[1]
for a in summarize.active_accounts(con):
    summarize.summarize_account(con, a["id"], a["name"], a["platform"], date)
    summarize.summarize_account_history(con, a["id"], a["name"], a["platform"], date)
    con.commit()
    print("done", a["name"], flush=True)
summarize.summarize(con, date); con.commit()
print("HOME DONE", flush=True)
PY
echo "ALL COMPLETE"
