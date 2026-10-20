#!/usr/bin/env bash
# Quick end-to-end check: one day from each source into a temporary directory.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PY=${PYTHON:-python}
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
DAY=${1:-$(date -d "3 days ago" +%F 2>/dev/null || date -v-3d +%F)}
OUT=${OUT:-$(mktemp -d)}
echo "smoke test for $DAY -> $OUT"
"$PY" -m paper_crawler all --start "$DAY" --end "$DAY" --out "$OUT" --batch-size 200
ls -R "$OUT" | head -40
