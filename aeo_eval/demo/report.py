"""Generate human-readable demo reports."""

from __future__ import annotations

import sqlite3
import json


def print_run_summary(db_path: str, run_id: str) -> None:
    """Print summary of a completed evaluation run."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get run metadata
    run = conn.execute(
        "SELECT * FROM evaluation_runs WHERE run_id = ?", (run_id,)
    ).fetchone()

    if not run:
        print(f"Run {run_id} not found")
        return

    print(f"\n=== Evaluation Run: {run_id} ===")
    print(f"Engine: {run['engine']}, Model: {run['model']}")
    print(f"Prompts: {run['num_prompts']}, Cost: ${run['cost']:.2f}")

    # Visibility metrics
    print("\n--- Visibility Metrics ---")
    metrics = conn.execute(
        """
        SELECT dimension_value, striim_mention_rate, striim_top3_rate,
               striim_citation_rate, num_responses
        FROM visibility_metrics
        WHERE run_id = ? AND dimension = 'by_topic'
        LIMIT 5
        """,
        (run_id,),
    ).fetchall()

    for row in metrics:
        topic, mention_rate, top3_rate, citation_rate, num = row
        print(
            f"{topic}: {mention_rate:.0%} mention, "
            f"{top3_rate:.0%} top-3, {citation_rate:.0%} cited (n={num})"
        )

    # Gaps
    print("\n--- Detected Gaps ---")
    gaps = conn.execute(
        """
        SELECT id, topic, gap_type, priority, striim_visibility,
               top_competitor_visibility, top_competitor_name
        FROM gaps
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()

    for gap_id, topic, gap_type, priority, striim_vis, comp_vis, comp_name in gaps:
        print(
            f"[{priority.upper()}] {topic} - {gap_type}: "
            f"Striim {striim_vis:.0%} vs {comp_name} {comp_vis:.0%}"
        )

    # Recommendations
    print("\n--- Recommendations (Auto-Approved) ---")
    recs = conn.execute(
        """
        SELECT r.id, r.problem, r.recommended_action, r.priority, r.status
        FROM recommendations r
        JOIN gaps g ON r.gap_id = g.id
        WHERE g.run_id = ? AND r.status = 'approved'
        LIMIT 5
        """,
        (run_id,),
    ).fetchall()

    for rec_id, problem, action, priority, status in recs:
        print(f"\nPriority {priority}: {action}")

    conn.close()
    print("\n")
