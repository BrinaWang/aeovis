"""Live progress reporting for pipeline runs started from the dashboard.

The pipeline runs in a background thread; the page polls the database
through these helpers to show which stage the run is in. They are pure
DB reads so the Streamlit layer stays a thin render loop.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Optional

# Statuses that mean run_full_pipeline has finished (or evaluation
# failed outright). "processing" is the post-evaluation window where
# gaps and recommendations are still being generated.
_FINAL_STATUSES = frozenset({"completed", "partial_failure", "failed"})


def fetch_run_progress(conn: sqlite3.Connection, started_after: str) -> Optional[Dict]:
    """Snapshot of the newest run started at or after ``started_after``.

    Returns None while the evaluator has not created the run row yet.
    """
    row = conn.execute(
        """
        SELECT run_id, status, num_prompts FROM evaluation_runs
        WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 1
        """,
        (started_after,),
    ).fetchone()
    if row is None:
        return None
    run_id, status, num_prompts = row

    def _count(sql: str) -> int:
        return conn.execute(sql, (run_id,)).fetchone()[0]

    return {
        "run_id": run_id,
        "status": status,
        "num_prompts": num_prompts,
        "responses": _count(
            "SELECT COUNT(*) FROM raw_responses WHERE run_id = ?"
        ),
        "analyzed": _count(
            "SELECT COUNT(*) FROM response_analysis ra"
            " JOIN raw_responses rr ON rr.id = ra.raw_response_id"
            " WHERE rr.run_id = ?"
        ),
        "gaps": _count("SELECT COUNT(*) FROM gaps WHERE run_id = ?"),
        "recommendations": _count(
            "SELECT COUNT(*) FROM recommendations r"
            " JOIN gaps g ON g.id = r.gap_id WHERE g.run_id = ?"
        ),
        "done": status in _FINAL_STATUSES,
    }


def describe_progress(progress: Optional[Dict], requested: int) -> str:
    """One-line human description of where the run currently is."""
    if progress is None:
        return "Starting evaluation…"
    if progress["done"]:
        return f"Finished ({progress['status']})"
    if progress["status"] == "processing":
        if progress["gaps"] == 0:
            return "Computing metrics, citations and gaps…"
        return (
            f"Generating recommendations for {progress['gaps']} gaps… "
            "(this is the longest stage)"
        )
    return (
        f"Answering and analyzing questions "
        f"({progress['analyzed']}/{requested} analyzed, "
        f"{progress['responses']}/{requested} answered)"
    )
