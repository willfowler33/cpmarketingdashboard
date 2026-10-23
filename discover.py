"""Auto-generate accounts.yaml by asking both APIs which accounts we can see.

Google: all non-manager client accounts under the MCC (login_customer_id).
Meta: all ad accounts the system-user token can access.

Run after credentials are in place:  ./venv/bin/python discover.py
Review/edit the generated accounts.yaml (set client names), then run run_daily.py.
"""
import os

import requests
import yaml

GRAPH = "https://graph.facebook.com/v23.0"


def google_accounts():
    from google.ads.googleads.client import GoogleAdsClient
    client = GoogleAdsClient.load_from_storage(os.environ.get("GOOGLE_ADS_YAML", "google-ads.yaml"))
    svc = client.get_service("GoogleAdsService")
    mcc = str(client.login_customer_id)
    query = """
        SELECT customer_client.id, customer_client.descriptive_name,
               customer_client.manager, customer_client.status
        FROM customer_client WHERE customer_client.level <= 1
    """
    out = []
    for row in svc.search(customer_id=mcc, query=query):
        cc = row.customer_client
        if not cc.manager and cc.status.name == "ENABLED":
            out.append({"account_id": str(cc.id), "name": cc.descriptive_name or str(cc.id), "client": ""})
    return out


def meta_accounts():
    token = os.environ["META_ACCESS_TOKEN"]
    out, url = [], f"{GRAPH}/me/adaccounts"
    params = {"fields": "account_id,name,account_status", "limit": 200, "access_token": token}
    while url:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        for a in body.get("data", []):
            if a.get("account_status") == 1:  # active
                out.append({"account_id": a["account_id"], "name": a.get("name", a["account_id"]), "client": ""})
        url = body.get("paging", {}).get("next")
        params = {}
    return out


def main():
    result, errors = {}, []
    for key, fn in (("google", google_accounts), ("meta", meta_accounts)):
        try:
            result[key] = fn()
            print(f"{key}: found {len(result[key])} active accounts")
        except Exception as e:
            errors.append(f"{key}: {e}")
            result[key] = []
    with open("accounts.yaml", "w") as f:
        yaml.safe_dump(result, f, sort_keys=False, allow_unicode=True)
    print("wrote accounts.yaml — review it and fill in client names")
    if errors:
        print("ERRORS:", *errors, sep="\n  ")


if __name__ == "__main__":
    main()
