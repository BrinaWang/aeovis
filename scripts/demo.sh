#!/bin/bash
# Quick demo: run a small evaluation and display results

set -e

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_DIR"

echo "=== AEO Visibility Platform Demo ==="
echo ""
echo "Running 5 sample questions..."
python -m aeo_eval.cli run --engine claude --limit 5 --db data/demo.db 2>&1 | tail -5

RUN_ID=$(sqlite3 data/demo.db "SELECT run_id FROM evaluation_runs ORDER BY timestamp DESC LIMIT 1" 2>/dev/null || echo "")
if [ -z "$RUN_ID" ]; then
    echo "Error: could not find run ID"
    exit 1
fi

echo "Run ID: $RUN_ID"

echo ""
echo "Generating report..."
python -m aeo_eval.cli report "$RUN_ID" --db data/demo.db

echo ""
echo "Demo complete!"
