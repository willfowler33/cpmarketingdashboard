#!/bin/bash
cd /opt/ads-visibility
set -a; . ./.env; set +a
DATE="${1:-2026-08-11}"
./venv/bin/python -c "import db,summarize; t=summarize.summarize(db.connect(),'$DATE'); open('last_summary.txt','w').write(t); print('done', len(t))"
