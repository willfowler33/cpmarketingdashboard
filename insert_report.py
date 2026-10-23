"""Insert a specialist report from JSON on stdin: {date, author, subject, body}.
Used by the daily scheduled task:  echo '<json>' | ./venv/bin/python insert_report.py
"""
import datetime as dt
import json
import sys

import db

# Read JSON from a file arg (robust) or stdin.
if len(sys.argv) > 1:
    with open(sys.argv[1]) as f:
        data = json.load(f)
else:
    data = json.load(sys.stdin)
body = (data.get("body") or "").strip()
if not body:
    print("empty body, skipped")
    sys.exit(0)
date = data.get("date") or dt.date.today().isoformat()
con = db.connect()
con.execute(
    "INSERT OR REPLACE INTO specialist_reports(date, author, subject, body, source, received_at) "
    "VALUES(?,?,?,?,?,?)",
    (date, data.get("author", "Simi Brown"), data.get("subject", ""), body,
     "gmail-task", dt.datetime.now().isoformat()))
con.commit()
print("stored report for", date)
