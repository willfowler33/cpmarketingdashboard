# CP Marketing Dashboard

Daily visibility into every Facebook (Meta) and Google ad account The Concrete Protector manages —
for Incredible Products and contractor clients. It captures not just the metrics but the actual
management process: what changed in each account, when, and (in plain English) why.

Live at **marketingdashboard.theconcreteprotector.com**, served from an always-on box (skald-box)
through a Cloudflare tunnel.

## What it does

- **Nightly collection** (cron on skald-box, 6:15am): pulls change history and performance from the
  Meta Marketing API and Google Ads API into a local SQLite archive, so it outlives the APIs' own
  short history windows (Google change events are capped at ~30 days; Meta activities go back
  further).
- **Metrics**: spend, lead volume, CPL, CPC, CPM, CTR, conversion rate — plus revenue / ROAS /
  purchases for e-commerce accounts (e.g. Sanitred on Google).
- **Per-account "management narrative"**: one running, plain-English bullet per day of every action
  taken (budget changes, pauses, new ad groups, creative, targeting), newest first, back to each
  account's launch — written by a cheap LLM via OpenRouter, with the *why* tied to the real numbers.
- **Specialist report archive**: the ads specialist's daily update emails are pulled from Gmail
  (6:30am cron) and shown on the home page as the human context behind the changes.

## Layout

| File | Purpose |
|------|---------|
| `dashboard.py` | Flask HUD + per-account pages + `/ingest/email` endpoint |
| `db.py` | SQLite schema + helpers (WAL, migrations) |
| `collect_google.py` / `collect_meta.py` | Daily change + metric collectors |
| `summarize.py` | Account narratives + portfolio brief (OpenRouter + deterministic fallbacks) |
| `run_daily.py` / `run.sh` | Nightly orchestrator |
| `gmail_pull.py` | Pull the specialist's daily update email from Gmail |
| `discover.py` | Auto-build `accounts.yaml` from the APIs |
| `deep_history.py` | One-time deep Meta history backfill |
| `backfill30.py`, `gen_*`, `regen_*`, `finish.sh` | One-off backfill / regeneration helpers |

## Config (not committed — see `.gitignore`)

- `google-ads.yaml` — Google Ads API creds (developer token, OAuth client, refresh token, MCC id)
- `.env` — `META_ACCESS_TOKEN`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`
- `gmail_token.json` — Gmail read-only OAuth token (for `gmail_pull.py`)
- `accounts.yaml` — the managed account list (built by `discover.py`)

Templates/examples: `google-ads.yaml.template`, `accounts.yaml.example`.

## Deploy (skald-box)

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
# drop in google-ads.yaml, .env, gmail_token.json, accounts.yaml
./venv/bin/python run_daily.py    # one collection run
./venv/bin/python dashboard.py    # serve on :8090 (behind the Cloudflare tunnel)
```

Cron:
```
15 6 * * * cd /opt/ads-visibility && ./run.sh >> run.log 2>&1
30 6 * * * cd /opt/ads-visibility && DAYS=3 ./venv/bin/python gmail_pull.py >> gmail_pull.log 2>&1
```
