"""SQLite archive for ad account changes, metrics, and daily summaries."""
import json
import os
import sqlite3

DB_PATH = os.environ.get("ADS_DB", os.path.join(os.path.dirname(__file__), "ads_visibility.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id          TEXT PRIMARY KEY,          -- platform:account_id
    platform    TEXT NOT NULL,             -- google | meta
    account_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    client      TEXT NOT NULL DEFAULT '',  -- e.g. Incredible Products, Sanitred, contractor name
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account     TEXT NOT NULL REFERENCES accounts(id),
    changed_at  TEXT NOT NULL,             -- ISO timestamp
    actor       TEXT,                      -- user email / actor name
    source      TEXT,                      -- UI, API, automated rule, etc.
    object_type TEXT,                      -- campaign, ad set, ad, budget...
    object_name TEXT,
    event_type  TEXT,                      -- platform event type
    detail      TEXT,                      -- JSON: old/new values, changed fields
    UNIQUE(account, changed_at, event_type, object_name, actor)
);

CREATE TABLE IF NOT EXISTS metrics (
    account     TEXT NOT NULL REFERENCES accounts(id),
    date        TEXT NOT NULL,             -- YYYY-MM-DD
    campaign_id TEXT NOT NULL,
    campaign    TEXT,
    spend       REAL, impressions INTEGER, clicks INTEGER,
    leads       REAL, ctr REAL, cpc REAL, cpm REAL, cpl REAL,
    revenue     REAL DEFAULT 0,            -- purchase value (ecom accounts)
    PRIMARY KEY (account, date, campaign_id)
);

CREATE TABLE IF NOT EXISTS summaries (
    date        TEXT PRIMARY KEY,          -- YYYY-MM-DD
    exec_summary TEXT NOT NULL,            -- markdown, aggregate home story
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS specialist_reports (
    date        TEXT PRIMARY KEY,          -- YYYY-MM-DD the report covers
    author      TEXT,                      -- e.g. Simi Brown
    subject     TEXT,
    body        TEXT NOT NULL,             -- the specialist's own words
    source      TEXT,                      -- gmail-backfill | email-cc
    received_at TEXT
);

CREATE TABLE IF NOT EXISTS account_summaries (
    account     TEXT NOT NULL,             -- accounts.id
    date        TEXT NOT NULL,             -- YYYY-MM-DD
    story       TEXT NOT NULL,             -- markdown, per-entity story
    generated_at TEXT NOT NULL,
    PRIMARY KEY (account, date)
);

CREATE INDEX IF NOT EXISTS idx_changes_date ON changes(account, changed_at);
CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics(date);
"""


def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")     # readers don't block writers
    con.execute("PRAGMA busy_timeout=30000")   # wait up to 30s for a lock
    con.executescript(SCHEMA)
    # Migration: add revenue column to a metrics table that predates it.
    cols = [r[1] for r in con.execute("PRAGMA table_info(metrics)")]
    if "revenue" not in cols:
        con.execute("ALTER TABLE metrics ADD COLUMN revenue REAL DEFAULT 0")
    return con


def upsert_account(con, platform, account_id, name, client=""):
    key = f"{platform}:{account_id}"
    con.execute(
        "INSERT INTO accounts(id, platform, account_id, name, client) VALUES(?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, client=excluded.client",
        (key, platform, account_id, name, client),
    )
    return key


def insert_change(con, account, changed_at, actor, source, object_type, object_name, event_type, detail):
    con.execute(
        "INSERT OR IGNORE INTO changes(account, changed_at, actor, source, object_type, object_name, event_type, detail) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (account, changed_at, actor, source, object_type, object_name, event_type,
         json.dumps(detail, default=str) if not isinstance(detail, str) else detail),
    )


def insert_metrics(con, account, date, campaign_id, campaign, spend, impressions, clicks, leads, revenue=0):
    ctr = (clicks / impressions * 100) if impressions else 0
    cpc = (spend / clicks) if clicks else 0
    cpm = (spend / impressions * 1000) if impressions else 0
    cpl = (spend / leads) if leads else 0
    con.execute(
        "INSERT OR REPLACE INTO metrics(account, date, campaign_id, campaign, spend, impressions, clicks, leads, ctr, cpc, cpm, cpl, revenue) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (account, date, campaign_id, campaign, spend, impressions, clicks, leads, ctr, cpc, cpm, cpl, revenue),
    )
