"""Pull the full available change history (Meta activities go back further than 30 days).
Google ChangeEvent is capped at 30 days by the API, so only Meta deepens here."""
import datetime as dt
import os

import yaml

import db
import collect_meta as cm

DAYS_BACK = int(os.environ.get("DEEP_DAYS", "180"))


def main():
    cfg = yaml.safe_load(open("accounts.yaml"))
    con = db.connect()
    since = (dt.date.today() - dt.timedelta(days=DAYS_BACK)).isoformat() + "T00:00:00"
    until = dt.date.today().isoformat() + "T23:59:59"
    total = 0
    for acct in cfg.get("meta", []):
        aid = str(acct["account_id"])
        aid = aid if aid.startswith("act_") else f"act_{aid}"
        key = db.upsert_account(con, "meta", aid, acct["name"], acct.get("client", ""))
        try:
            evs = cm._get(f"{cm.GRAPH}/{aid}/activities",
                          {"fields": cm.ACTIVITY_FIELDS, "since": since, "until": until})
        except Exception as e:
            print("err", acct["name"], e)
            continue
        for ev in evs:
            db.insert_change(
                con, key, changed_at=ev.get("event_time", ""), actor=ev.get("actor_name", ""),
                source=ev.get("application_name", "Ads Manager"), object_type=ev.get("object_type", ""),
                object_name=ev.get("object_name", ""),
                event_type=ev.get("translated_event_type") or ev.get("event_type", ""),
                detail=ev.get("extra_data", ""))
        con.commit()
        total += len(evs)
        print(f"{acct['name']}: {len(evs)} activities", flush=True)
    print("total", total, flush=True)


if __name__ == "__main__":
    main()
