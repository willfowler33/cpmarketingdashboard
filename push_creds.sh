#!/bin/bash
# Collects the four credential values and pushes them to skald-box.
# Secrets never leave your machines (straight Mac -> skald-box over SSH).
set -e
export PATH=$PATH:/opt/homebrew/bin:/usr/local/bin

CS=$(ls -t ~/Downloads/client_secret_2_900116815469*.json 2>/dev/null | head -1)
[ -z "$CS" ] && CS=$(ls -t ~/Downloads/client_secret*900116815469*.json 2>/dev/null | head -1)
echo "OAuth client file: $CS"
CID=$(python3 -c "import json;d=json.load(open('$CS'));k='installed' if 'installed' in d else 'web';print(d[k]['client_id'])")
CSEC=$(python3 -c "import json;d=json.load(open('$CS'));k='installed' if 'installed' in d else 'web';print(d[k]['client_secret'])")

echo
echo "Paste each value and press Enter."
read -p "1) Google Ads REFRESH TOKEN (just printed above): " RT
read -p "2) Google Ads DEVELOPER TOKEN (from API Center): " DEV
read -p "3) META system-user token: " META
read -p "4) ANTHROPIC API key (console.anthropic.com): " ANTH

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
echo "=== Credentials loaded onto skald-box. Tell Claude 'creds loaded'. ==="
