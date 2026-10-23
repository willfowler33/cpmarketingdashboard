"""Nightly orchestrator: collect yesterday's changes + metrics, then generate the exec summary.

Cron (skald-box):  15 6 * * *  cd /opt/ads-visibility && ./venv/bin/python run_daily.py >> run.log 2>&1
Test without credentials:  MOCK=1 python run_daily.py
"""
import datetime as dt
import os
import sys

import yaml

import collect_google
import collect_meta
import db
import summarize


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else (dt.date.today() - dt.timedelta(days=1)).isoformat()
    with open(os.path.join(os.path.dirname(__file__), "accounts.yaml")) as f:
        cfg = yaml.safe_load(f)

    con = db.connect()
    errors = []
    for name, mod, key in (("google", collect_google, "google"), ("meta", collect_meta, "meta")):
        try:
            mod.collect(con, cfg.get(key, []), date)
            con.commit()
        except Exception as e:  # one platform failing shouldn't kill the report
            errors.append(f"{name}: {e}")

    try:
        summarize.summarize_all(con, date)
        con.commit()
    except Exception as e:
        errors.append(f"summarize: {e}")

    print(f"[{dt.datetime.now().isoformat()}] done for {date}. errors: {errors or 'none'}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
