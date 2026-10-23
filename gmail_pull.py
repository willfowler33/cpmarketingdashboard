"""Pull Simi's latest 'Daily Update' email(s) from Gmail and store in specialist_reports.
Runs on skald-box via cron (always-on). Window via DAYS env (default 3; large for backfill).

Usage:  ./venv/bin/python gmail_pull.py          # last 3 days
        DAYS=30 ./venv/bin/python gmail_pull.py  # backfill 30 days
"""
import base64
import datetime as dt
import os
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import db

HERE = os.path.dirname(os.path.abspath(__file__))
TOK = os.path.join(HERE, "gmail_token.json")
DAYS = int(os.environ.get("DAYS", "3"))


def _service():
    import json
    t = json.load(open(TOK))
    creds = Credentials(None, refresh_token=t["refresh_token"], token_uri=t["token_uri"],
                        client_id=t["client_id"], client_secret=t["client_secret"],
                        scopes=["https://www.googleapis.com/auth/gmail.readonly"])
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _plain_body(payload):
    """Walk the MIME tree for the text/plain part."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    for p in payload.get("parts", []) or []:
        txt = _plain_body(p)
        if txt:
            return txt
    # fall back to html stripped
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        html = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
        return re.sub(r"<[^>]+>", "", html)
    return ""


def _clean(body):
    out = []
    for line in body.replace("\r", "").split("\n"):
        s = line.strip()
        if "[image:" in s:
            continue
        if "docs.google.com" in s or "drive.google.com" in s:
            continue
        if s.lower() in ("tks", "thanks", "thank you!", "thank you", "hey!", "hello,"):
            continue
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _date_from_subject(subject, fallback):
    m = re.search(r"(\d{1,2})/(\d{1,2})", subject or "")
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        try:
            return dt.date(dt.date.today().year, mo, dy).isoformat()
        except ValueError:
            pass
    return fallback


def main():
    svc = _service()
    q = f'from:simi@theconcreteprotector.com subject:"Daily Update" newer_than:{DAYS}d'
    res = svc.users().messages().list(userId="me", q=q, maxResults=100).execute()
    msgs = res.get("messages", [])
    con = db.connect()
    stored = 0
    for m in msgs:
        full = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
        subject = headers.get("subject", "")
        sent = dt.datetime.fromtimestamp(int(full["internalDate"]) / 1000).date().isoformat()
        date = _date_from_subject(subject, sent)
        body = _clean(_plain_body(full["payload"]))
        if not body:
            continue
        con.execute(
            "INSERT OR REPLACE INTO specialist_reports(date, author, subject, body, source, received_at) "
            "VALUES(?,?,?,?,?,?)",
            (date, "Simi Brown", subject, body, "gmail-api", dt.datetime.now().isoformat()))
        con.commit()
        stored += 1
        print("stored", date, flush=True)
    print(f"done: {stored} report(s) from last {DAYS} days", flush=True)


if __name__ == "__main__":
    main()
