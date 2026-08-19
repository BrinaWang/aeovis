"""Dashboard citation counts must be run-scoped and non-zero."""
import json
import sqlite3
import uuid

from aeo_eval.config import config as app_config
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed_citation(conn, run_id, analysis_id, domain, category):
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine) VALUES (?, ?, 'p1', 'mock')",
        (rr_id, run_id),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, striim_recommended, citations) "
        "VALUES (?, ?, 1, 0, ?)",
        (analysis_id, rr_id, json.dumps([])),
    )
    url = f"https://{domain}/{uuid.uuid4().hex[:6]}"
    cit_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO citations (id, url, normalized_url, domain, source_category, "
        "first_observed, last_observed, occurrence_count) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1)",
        (cit_id, url, url, domain, category),
    )
    conn.execute(
        "INSERT INTO citation_occurrences (id, citation_id, response_analysis_id) "
        "VALUES (?, ?, ?)",
        (str(uuid.uuid4()), cit_id, analysis_id),
    )
    conn.commit()


def test_fetch_citations_scoped_to_run(tmp_path, monkeypatch):
    db = tmp_path / "dash.db"
    monkeypatch.setattr(app_config.general, "output_db_path", db)
    SQLiteStore(str(db)).init_db()
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON")
    seed_citation(conn, "run-1", "an-1", "fivetran.com", "competitor")
    seed_citation(conn, "run-1", "an-2", "fivetran.com", "competitor")
    seed_citation(conn, "run-2", "an-3", "estuary.dev", "competitor")
    conn.close()

    from aeo_eval.dashboard.app import fetch_citations_for_run

    rows = fetch_citations_for_run("run-1")
    assert len(rows) == 1
    assert rows[0]["domain"] == "fivetran.com"
    assert rows[0]["citation_count"] == 2  # run-2's estuary.dev excluded
