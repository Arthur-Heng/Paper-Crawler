#!/usr/bin/env bash
# Collect everything added to PubMed, bioRxiv and medRxiv in the last 30 days.
# Usage: scripts/collect_last_month.sh [extra paper-crawler args, e.g. --days 60 --out /path]
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PY=${PYTHON:-python}
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
exec "$PY" -m paper_crawler all --days 30 --out data "$@"
