"""Metric rates must come from stored data, not approximations."""
import json
import sqlite3

from aeo_eval.metrics.calculator import MetricsCalculator
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed_response(conn, run_id, analysis_id, *, topic="Oracle CDC",
                  mentioned=1, recommended=0, citations=None):
    prompt_id = f"p-{topic}"
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO prompts (id, prompt_text, topic, persona, intent, priority) "
        "VALUES (?, 'q', ?, 'x', 'y', 'high')",
        (prompt_id, topic),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine) VALUES (?, ?, ?, 'mock')",
        (rr_id, run_id, prompt_id),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, "
        "striim_recommended, citations, brands_found) VALUES (?, ?, ?, ?, ?, '[]')",
        (analysis_id, rr_id, mentioned, recommended, json.dumps(citations or [])),
    )
    conn.commit()


def make_conn(tmp_path):
    db = str(tmp_path / "t.db")
    SQLiteStore(db).init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_recommendation_rate_uses_stored_flag(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", mentioned=1, recommended=1)
    seed_response(conn, "run-1", "an-2", mentioned=1, recommended=0)
    metrics = MetricsCalculator(conn).calculate_metrics_for_run("run-1")
    assert metrics["mention_rate"] == 1.0
    assert metrics["recommendation_rate"] == 0.5


def test_by_topic_recommendation_rate(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", recommended=1)
    seed_response(conn, "run-1", "an-2", recommended=0)
    by_topic = MetricsCalculator(conn).calculate_metrics_by_topic("run-1")
    assert by_topic[0]["recommendation_rate"] == 0.5


def test_citation_rate_is_share_of_responses_citing_striim(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1",
                  citations=["https://www.striim.com/docs/", "https://ex.com/a"])
    seed_response(conn, "run-1", "an-2", citations=["https://ex.com/b"])
    metrics = MetricsCalculator(conn).calculate_metrics_for_run("run-1")
    assert metrics["citation_rate"] == 0.5


def test_citation_rate_cannot_exceed_one(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", citations=[
        "https://www.striim.com/a", "https://www.striim.com/b",
        "https://www.striim.com/c",
    ])
    metrics = MetricsCalculator(conn).calculate_metrics_for_run("run-1")
    assert metrics["citation_rate"] == 1.0


def test_by_topic_citation_rate_not_hardcoded_zero(tmp_path):
    conn = make_conn(tmp_path)
    seed_response(conn, "run-1", "an-1", citations=["https://www.striim.com/x"])
    by_topic = MetricsCalculator(conn).calculate_metrics_by_topic("run-1")
    assert by_topic[0]["citation_rate"] == 1.0
