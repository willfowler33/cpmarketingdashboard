#!/bin/bash
cd /opt/ads-visibility
grep -q OPENROUTER_MODEL .env || echo "OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free" >> .env
set -a; . ./.env; set +a
for d in 5 4 3 2 1; do
  D=$(date -d "-$d day" +%F)
  ./venv/bin/python -c "import db,summarize; summarize.summarize(db.connect(),'$D')" 2>>summ.err && echo "ok $D" || echo "FAIL $D"
done
./venv/bin/python -c "import db; print('summaries now:', db.connect().execute('select count(*) from summaries').fetchone()[0])"
