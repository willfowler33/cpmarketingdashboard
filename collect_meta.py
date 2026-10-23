"""Pull yesterday's activity log + campaign insights from Meta Marketing API.

Requires META_ACCESS_TOKEN (long-lived system-user token) — see README.
MOCK=1 inserts sample data.
"""
import datetime as dt
import json
import os

import requests

import db

MOCK = os.environ.get("MOCK") == "1"
GRAPH = "https://graph.facebook.com/v23.0"
ACTIVITY_FIELDS = "event_time,event_type,translated_event_type,actor_name,object_name,object_type,extra_data,application_name"
INSIGHT_FIELDS = "campaign_id,campaign_name,spend,impressions,clicks,actions,action_values"


def _get(url, params):
    """GET with cursor pagination."""
    token = os.environ["META_ACCESS_TOKEN"]
    out = []
    params = dict(params, access_token=token, limit=500)
    while url:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        out.extend(body.get("data", []))
        url = body.get("paging", {}).get("next")
        params = {}  # next URL already carries params
    return out


def _is_lead_action(t):
    t = t or ""
    if t in ("lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead", "leadgen_grouped"):
        return True
    # Meta's unified lead metrics, e.g. offsite_complete_registration_add_meta_leads
    if t.endswith("_add_meta_leads"):
        return True
    # Custom conversions the account defined (form submissions on lead-gen campaigns),
    # e.g. offsite_conversion.custom.970667781911969
    return t.startswith("offsite_conversion.custom.")


def _leads(actions):
    # Several action_types report the SAME leads under different attributions
    # (e.g. offsite_complete_registration_add_meta_leads and offsite_search_add_meta_leads
    # both = 70). Take the max to match Ads Manager's result count without double-counting.
    vals = [float(a.get("value", 0)) for a in (actions or []) if _is_lead_action(a.get("action_type"))]
    return max(vals) if vals else 0.0


def _revenue(action_values):
    # Purchase value for ecom accounts.
    for a in action_values or []:
        if a.get("action_type") in ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase"):
            return float(a.get("value", 0))
    return 0.0


def collect(con, accounts, date):
    if MOCK:
        _mock(con, accounts, date)
        return
    since = f"{date}T00:00:00"
    until = f"{date}T23:59:59"
    for acct in accounts:
        aid = str(acct["account_id"])
        aid = aid if aid.startswith("act_") else f"act_{aid}"
        key = db.upsert_account(con, "meta", aid, acct["name"], acct.get("client", ""))

        for ev in _get(f"{GRAPH}/{aid}/activities", {"fields": ACTIVITY_FIELDS, "since": since, "until": until}):
            db.insert_change(
                con, key,
                changed_at=ev.get("event_time", ""),
                actor=ev.get("actor_name", ""),
                source=ev.get("application_name", "Ads Manager"),
                object_type=ev.get("object_type", ""),
                object_name=ev.get("object_name", ""),
                event_type=ev.get("translated_event_type") or ev.get("event_type", ""),
                detail=ev.get("extra_data", ""),
            )

        for row in _get(f"{GRAPH}/{aid}/insights", {
            "fields": INSIGHT_FIELDS, "level": "campaign",
            "time_range": json.dumps({"since": date, "until": date}),
        }):
            db.insert_metrics(
                con, key, date,
                campaign_id=row.get("campaign_id", ""),
                campaign=row.get("campaign_name", ""),
                spend=float(row.get("spend", 0)),
                impressions=int(row.get("impressions", 0)),
                clicks=int(row.get("clicks", 0)),
                leads=_leads(row.get("actions")),
                revenue=_revenue(row.get("action_values")),
            )


def _mock(con, accounts, date):
    for acct in accounts:
        key = db.upsert_account(con, "meta", f"act_{acct['account_id']}", acct["name"], acct.get("client", ""))
        db.insert_change(con, key, f"{date}T09:02:11", "Ads Specialist", "Ads Manager",
                         "AD", "GraniFlex Lead Gen v3", "Ad paused",
                         json.dumps({"old_value": "ACTIVE", "new_value": "PAUSED"}))
        db.insert_metrics(con, key, date, "23851", "GraniFlex Lead Gen", 112.50, 15200, 310, 9)
