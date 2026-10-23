#!/bin/bash
cd /opt/ads-visibility
set -a; . ./.env; set +a
./venv/bin/python discover.py > discover_final.log 2>&1
./venv/bin/python backfill30.py > final_run.log 2>&1
echo "FINAL COMPLETE" >> final_run.log
