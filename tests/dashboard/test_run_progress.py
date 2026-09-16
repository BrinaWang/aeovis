"""Tests for the dashboard's live run-progress helpers."""

import json
import sqlite3
from pathlib import Path

from aeo_eval.dashboard.progress import fetch_run_progress, describe_progress

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "aeo_eval" / "storage" / "sqlite_schema.sql"


def _conn_with_run(status="success", responses=0, analyzed=0, gaps=0, recs=0):
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts, status, cost)"
        " VALUES ('run-1', '2026-09-15T23:00:00', 'claude', 'claude-sonnet-5', 5, ?, 0)",
        (status,),
    )
    for i in range(responses):
        conn.execute(
            "INSERT INTO raw_responses (id, run_id, prompt_id, engine, status)"
            " VALUES (?, 'run-1', ?, 'claude', 'success')",
            (f"r{i}", f"p{i}"),
        )
    for i in range(analyzed):
        conn.execute(
            "INSERT INTO response_analysis (id, raw_response_id) VALUES (?, ?)",
            (f"a{i}", f"r{i}"),
        )
    for i in range(gaps):
        conn.execute(
            "INSERT INTO gaps (id, topic, gap_type, affected_prompts, evidence_ids,"
            " priority, confidence, run_id, created_timestamp)"
            " VALUES (?, 'T', 'visibility', ?, ?, 'high', 'high', 'run-1', '2026-09-15T23:05:00')",
            (f"g{i}", json.dumps([]), json.dumps([])),
        )
    for i in range(recs):
        conn.execute(
            "INSERT INTO recommendations (id, gap_id, problem, recommended_action,"
            " status, created_timestamp)"
            " VALUES (?, 'g0', 'p', 'a', 'draft', '2026-09-15T23:10:00')",
            (f"rec{i}",),
        )
    conn.commit()
    return conn


def test_no_run_after_cutoff_returns_none():
    conn = _conn_with_run()
    assert fetch_run_progress(conn, "2026-09-15T23:30:00") is None


def test_counts_reflect_pipeline_state():
    conn = _conn_with_run(status="processing", responses=5, analyzed=5, gaps=3)
    progress = fetch_run_progress(conn, "2026-09-15T22:59:00")
    assert progress["run_id"] == "run-1"
    assert progress["status"] == "processing"
    assert progress["responses"] == 5
    assert progress["analyzed"] == 5
    assert progress["gaps"] == 3
    assert progress["recommendations"] == 0


def test_describe_answering_stage_shows_counts():
    conn = _conn_with_run(status="success", responses=2, analyzed=1)
    progress = fetch_run_progress(conn, "2026-09-15T22:59:00")
    text = describe_progress(progress, requested=5)
    assert "1/5" in text


def test_describe_processing_stage_mentions_recommendations_once_gaps_exist():
    conn = _conn_with_run(status="processing", responses=5, analyzed=5, gaps=3)
    progress = fetch_run_progress(conn, "2026-09-15T22:59:00")
    text = describe_progress(progress, requested=5)
    assert "recommendation" in text.lower()
    assert "3" in text


def test_describe_before_run_row_exists():
    assert "start" in describe_progress(None, requested=5).lower()


def test_placeholder_run_row_is_visible_to_progress_poll(tmp_path):
    """The dashboard finds a run by ``timestamp >= <ISO start>`` while it is
    still answering, i.e. when only save_run's placeholder row exists. That
    row must therefore carry the batch's ISO timestamp, not SQLite's
    space-separated UTC ``datetime('now')`` (which sorts before any ISO
    string of the same date)."""
    from datetime import datetime
    from aeo_eval.models.result import RunResult
    from aeo_eval.storage.sqlite_store import SQLiteStore

    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    batch_started = datetime(2030, 1, 1, 12, 0, 0)
    store.save_run(RunResult(
        run_id="r1", run_batch_id="batch-1", prompt_id="p1", engine="mock",
        model="mock-v1", status="success", response_text="x", error=None,
        latency_ms=1, run_timestamp=batch_started,
    ))

    conn = sqlite3.connect(db)
    progress = fetch_run_progress(conn, datetime(2030, 1, 1, 11, 59, 59).isoformat())
    assert progress is not None
    assert progress["run_id"] == "batch-1"
    assert progress["responses"] == 1


def test_finished_states_are_marked_done():
    for status in ("completed", "partial_failure", "failed"):
        conn = _conn_with_run(status=status, responses=5, analyzed=5)
        progress = fetch_run_progress(conn, "2026-09-15T22:59:00")
        assert progress["done"] is True, status
    conn = _conn_with_run(status="processing", responses=5, analyzed=5)
    assert fetch_run_progress(conn, "2026-09-15T22:59:00")["done"] is False
