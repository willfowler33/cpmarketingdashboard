"""Run ONCE on Will's Mac to mint the Google Ads refresh token.

Usage:  python3 get_refresh_token.py ~/Downloads/client_secret_XXXX.json
Opens a browser for consent (log in as will@theconcreteprotector.com), then
prints the refresh token to paste into google-ads.yaml on skald-box.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]

flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], scopes=SCOPES)
creds = flow.run_local_server(port=0, prompt="consent")
print("\n\nREFRESH TOKEN (paste into google-ads.yaml):\n")
print(creds.refresh_token)
