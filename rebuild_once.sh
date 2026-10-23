#!/bin/bash
# Single-instance rebuild: flock prevents concurrent runs (which cause DB locks).
exec 9>/opt/ads-visibility/.rebuild.lock
flock -n 9 || { echo "already running"; exit 0; }
cd /opt/ads-visibility
set -a; . ./.env; set +a
./venv/bin/python backfill30.py > rebuild.log 2>&1
echo "REBUILD DONE" >> rebuild.log
