"""Wrapper to run dashboard from project root."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Now import and run the dashboard
from aeo_eval.dashboard.app import main

if __name__ == "__main__":
    main()
