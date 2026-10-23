#!/bin/bash
# Runs on Will's Mac. Mints the Google refresh token and pushes all credentials
# straight to skald-box. Secrets never leave Will's machines.
set -e
cd "$(dirname "$0")"
export PATH=$PATH:/opt/homebrew/bin:/usr/local/bin

echo "=== Ads Visibility credential setup ==="

CS_JSON=$(ls -t ~/Downloads/client_secret*.json 2>/dev/null | head -1)
if [ -z "$CS_JSON" ]; then
  read -p "Path to the OAuth client JSON you downloaded: " CS_JSON
fi
echo "Using OAuth client file: $CS_JSON"

echo "Installing Google auth helper (one time)..."
python3 -m pip install --quiet --user google-auth-oauthlib 2>/dev/null || \
  python3 -m pip install --quiet --user --break-system-packages google-auth-oauthlib

echo
echo "A browser window will open — sign in as will@theconcreteprotector.com and approve."
RT=$(python3 get_refresh_token.py "$CS_JSON" | tail -1)
if [ -z "$RT" ]; then echo "No refresh token captured — rerun."; exit 1; fi
echo "Refresh token captured."

CID=$(python3 -c "import json,sys;d=json.load(open('$CS_JSON'));k='installed' if 'installed' in d else 'web';print(d[k]['client_id'])")
CSEC=$(python3 -c "import json,sys;d=json.load(open('$CS_JSON'));k='installed' if 'installed' in d else 'web';print(d[k]['client_secret'])")

echo
read -p "Paste the Google Ads DEVELOPER TOKEN (from API Center): " DEV
read -p "Paste the META system user token: " META
read -p "Paste the ANTHROPIC API key (from console.anthropic.com): " ANTH

TMP=$(mktemp -d)
cat > "$TMP/google-ads.yaml" <<EOF
developer_token: $DEV
client_id: $CID
client_secret: $CSEC
refresh_token: $RT
login_customer_id: "1943305382"
use_proto_plus: true
EOF
cat > "$TMP/.env" <<EOF
META_ACCESS_TOKEN=$META
ANTHROPIC_API_KEY=$ANTH
EOF

scp -q "$TMP/google-ads.yaml" "$TMP/.env" skald-box:ads-visibility/
rm -rf "$TMP"
ssh skald-box 'chmod 600 ads-visibility/google-ads.yaml ads-visibility/.env'
echo
echo "=== Done. Credentials are on skald-box. You can close this window. ==="
