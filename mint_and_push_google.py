"""Mint the Google refresh token and write google-ads.yaml straight to skald-box.
Will only approves a browser; the token is never shown to him or to Claude.

Usage: python3 mint_and_push_google.py <client_secret.json> <developer_token>
"""
import json
import subprocess
import sys
import tempfile

from google_auth_oauthlib.flow import InstalledAppFlow

cs_path, dev_token = sys.argv[1], sys.argv[2]
d = json.load(open(cs_path))
k = "installed" if "installed" in d else "web"
cid, csec = d[k]["client_id"], d[k]["client_secret"]

flow = InstalledAppFlow.from_client_secrets_file(cs_path, scopes=["https://www.googleapis.com/auth/adwords"])
creds = flow.run_local_server(port=0, prompt="consent")

yaml_text = f"""developer_token: {dev_token}
client_id: {cid}
client_secret: {csec}
refresh_token: {creds.refresh_token}
login_customer_id: "1943305382"
use_proto_plus: true
"""
with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
    f.write(yaml_text)
    tmp = f.name
subprocess.run(["scp", "-q", tmp, "skald-box:ads-visibility/google-ads.yaml"], check=True)
subprocess.run(["ssh", "skald-box", "chmod 600 ads-visibility/google-ads.yaml"], check=True)
print("\nGoogle credentials written to skald-box.")
