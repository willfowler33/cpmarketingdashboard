#!/bin/bash
cd /opt/ads-visibility
set -a; . ./.env; set +a
DATE="${1:-2026-08-11}"
./venv/bin/python - "$DATE" <<'PY'
import sys, db, summarize
con = db.connect()
date = sys.argv[1]
accts = summarize.active_accounts(con)
print("active accounts:", [a["name"] for a in accts])
for a in accts:
    summarize.summarize_account(con, a["id"], a["name"], a["platform"], date)
    con.commit()
    print("story:", a["name"])
summarize.summarize(con, date); con.commit()
print("home brief done")
PY
