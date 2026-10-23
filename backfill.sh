#!/bin/bash
cd /opt/ads-visibility
set -a; . ./.env; set +a
./venv/bin/python discover.py >/dev/null 2>&1
for d in $(seq 1 30); do
  D=$(date -d "-$d day" +%F)
  MOCK= ./venv/bin/python -c "
import sys,datetime as dt,yaml,db,collect_google,collect_meta
cfg=yaml.safe_load(open('accounts.yaml')); con=db.connect(); d=sys.argv[1]
try: collect_google.collect(con,cfg.get('google',[]),d)
except Exception as e: print('g',e)
try: collect_meta.collect(con,cfg.get('meta',[]),d)
except Exception as e: print('m',e)
con.commit()" "$D" 2>&1 | tail -1
  echo "collected $D"
done
./venv/bin/python - <<'PY'
import db
c=db.connect()
print("metrics rows:", c.execute("select count(*) from metrics").fetchone()[0])
print("changes:", c.execute("select count(*) from changes").fetchone()[0])
print("summaries:", c.execute("select count(*) from summaries").fetchone()[0])
print("accounts:", c.execute("select count(*) from accounts").fetchone()[0])
PY
