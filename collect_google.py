"""Pull yesterday's change events + campaign metrics from Google Ads.

Requires google-ads.yaml credentials (developer token, OAuth) — see README.
MOCK=1 inserts sample data so the pipeline can be tested before credentials exist.
"""
import datetime as dt
import json
import os

import db

MOCK = os.environ.get("MOCK") == "1"

CHANGE_QUERY = """
SELECT
  change_event.change_date_time,
  change_event.user_email,
  change_event.client_type,
  change_event.change_resource_type,
  change_event.resource_change_operation,
  change_event.changed_fields,
  change_event.old_resource,
  change_event.new_resource
FROM change_event
WHERE change_event.change_date_time >= '{start}'
  AND change_event.change_date_time <= '{end}'
LIMIT 10000
"""

METRICS_QUERY = """
SELECT
  campaign.id, campaign.name,
  metrics.cost_micros, metrics.impressions, metrics.clicks,
  metrics.conversions, metrics.conversions_value
FROM campaign
WHERE segments.date = '{date}'
  AND campaign.status != 'REMOVED'
"""


def collect(con, accounts, date):
    """accounts: list of dicts {account_id, name, client} from accounts.yaml."""
    if MOCK:
        _mock(con, accounts, date)
        return
    from google.ads.googleads.client import GoogleAdsClient
    client = GoogleAdsClient.load_from_storage(os.environ.get("GOOGLE_ADS_YAML", "google-ads.yaml"))
    svc = client.get_service("GoogleAdsService")

    start = f"{date} 00:00:00"
    end = f"{date} 23:59:59"
    for acct in accounts:
        cid = str(acct["account_id"]).replace("-", "")
        key = db.upsert_account(con, "google", cid, acct["name"], acct.get("client", ""))

        for row in svc.search(customer_id=cid, query=CHANGE_QUERY.format(start=start, end=end)):
            ce = row.change_event
            db.insert_change(
                con, key,
                changed_at=ce.change_date_time,
                actor=ce.user_email,
                source=ce.client_type.name if hasattr(ce.client_type, "name") else str(ce.client_type),
                object_type=ce.change_resource_type.name if hasattr(ce.change_resource_type, "name") else str(ce.change_resource_type),
                object_name="",
                event_type=ce.resource_change_operation.name if hasattr(ce.resource_change_operation, "name") else str(ce.resource_change_operation),
                detail={
                    "changed_fields": list(ce.changed_fields.paths),
                    "old": str(ce.old_resource)[:2000],
                    "new": str(ce.new_resource)[:2000],
                },
            )

        for row in svc.search(customer_id=cid, query=METRICS_QUERY.format(date=date)):
            db.insert_metrics(
                con, key, date,
                campaign_id=str(row.campaign.id),
                campaign=row.campaign.name,
                spend=row.metrics.cost_micros / 1_000_000,
                impressions=row.metrics.impressions,
                clicks=row.metrics.clicks,
                leads=row.metrics.conversions,
                revenue=row.metrics.conversions_value,
            )


def _mock(con, accounts, date):
    for acct in accounts:
        key = db.upsert_account(con, "google", str(acct["account_id"]), acct["name"], acct.get("client", ""))
        db.insert_change(con, key, f"{date} 10:14:22", "specialist@theconcreteprotector.com", "GOOGLE_ADS_WEB_CLIENT",
                         "CAMPAIGN_BUDGET", "Garage Floors - Search", "UPDATE",
                         {"changed_fields": ["amount_micros"], "old": "amount_micros: 50000000", "new": "amount_micros: 75000000"})
        db.insert_metrics(con, key, date, "111", "Garage Floors - Search", 74.10, 4210, 188, 6)
        db.insert_metrics(con, key, date, "112", "Basement Coatings - PMax", 55.00, 9800, 240, 3)
