#!/bin/bash
# Wait for the data rebuild to finish, then regenerate all stories with current prompts.
while pgrep -f backfill30.py >/dev/null; do sleep 10; done
exec 9>/opt/ads-visibility/.rebuild.lock
flock -n 9 || exit 0
cd /opt/ads-visibility
set -a; . ./.env; set +a
./venv/bin/python - <<'PY' > regen.log 2>&1
import datetime as dt, db, summarize
con = db.connect()
date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
for a in summarize.active_accounts(con):
    summarize.summarize_account(con, a["id"], a["name"], a["platform"], date)
    summarize.summarize_account_history(con, a["id"], a["name"], a["platform"], date)
    con.commit()
    print("regen", a["name"], flush=True)
summarize.summarize(con, date); con.commit()
print("REGEN COMPLETE", flush=True)
PY
