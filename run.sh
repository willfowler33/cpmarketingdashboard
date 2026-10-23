#!/bin/bash
cd "$(dirname "$0")"
set -a; . ./.env; set +a
./venv/bin/python run_daily.py "$@"
