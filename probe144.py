import os, requests
tok = os.environ["META_ACCESS_TOKEN"]
r = requests.get("https://graph.facebook.com/v23.0/act_144305066/insights",
                 params={"fields": "campaign_name,spend,actions", "level": "campaign",
                         "date_preset": "last_30d", "access_token": tok}, timeout=60)
for row in r.json().get("data", []):
    if "Training" in (row.get("campaign_name") or ""):
        print("CAMPAIGN:", row["campaign_name"], "spend", row.get("spend"))
        for a in row.get("actions", []):
            print("  ", a["action_type"], a["value"])
