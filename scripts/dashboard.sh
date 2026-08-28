#!/bin/bash
# AEO Visibility Platform Dashboard

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting AEO Visibility Dashboard"
echo ""
echo "Dashboard running at: http://localhost:8501"
echo "Press Ctrl+C to stop"
echo ""

cd "$PROJECT_ROOT"
streamlit run streamlit_app.py
