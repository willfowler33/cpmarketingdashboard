import json, sys, datetime as dt
import db
arr = json.load(open(sys.argv[1]))
con = db.connect()
n = 0
for data in arr:
    body = (data.get("body") or "").strip()
    if not body:
        print("empty body, skipped")
        continue
    date = data.get("date") or dt.date.today().isoformat()
    con.execute(
        "INSERT OR REPLACE INTO specialist_reports(date, author, subject, body, source, received_at) VALUES(?,?,?,?,?,?)",
        (date, data.get("author", "Simi Brown"), data.get("subject", ""), body, "gmail-task", dt.datetime.now().isoformat()))
    print("stored report for", date)
    n += 1
con.commit()
print("TOTAL_INSERTED", n)
