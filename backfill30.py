"""Collect 30 days of metrics + changes in ONE process, then generate all stories.
Logs progress to backfill30.log. Run detached: nohup ./venv/bin/python backfill30.py &"""
import datetime as dt
import sys

import yaml

import db
import collect_google
import collect_meta
import summarize

cfg = yaml.safe_load(open("accounts.yaml"))
con = db.connect()
today = dt.date.today()

for d in range(1, 31):
    date = (today - dt.timedelta(days=d)).isoformat()
    try:
        collect_meta.collect(con, cfg.get("meta", []), date)
    except Exception as e:
        print("meta", date, e, flush=True)
    try:
        collect_google.collect(con, cfg.get("google", []), date)
    except Exception as e:
        print("google", date, e, flush=True)
    con.commit()
    print("collected", date, flush=True)

print("METRICS DAYS:", con.execute("select count(distinct date) from metrics").fetchone()[0], flush=True)

date = (today - dt.timedelta(days=1)).isoformat()
for a in summarize.active_accounts(con):
    summarize.summarize_account(con, a["id"], a["name"], a["platform"], date)
    summarize.summarize_account_history(con, a["id"], a["name"], a["platform"], date)
    con.commit()
    print("story", a["name"], flush=True)
summarize.summarize(con, date)
con.commit()
print("ALL COMPLETE", flush=True)
