"""Citation persistence: history preserved across runs, occurrences written."""
import json
import sqlite3

from aeo_eval.citations.deduplicator import CitationDeduplicator
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed_analysis(db, run_id, analysis_id, citations):
    """Insert the minimal rows an analysis needs (run -> response -> analysis)."""
    store = SQLiteStore(db)
    store.init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
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
        (analysis_id, rr_id, json.dumps(citations)),
    )
    conn.commit()
    conn.close()


def make_citation(**overrides):
    base = {
        "original_url": "https://ex.com/a?x=1",
        "normalized_url": "https://ex.com/a",
        "domain": "ex.com",
        "source_category": "other",
        "occurrence_count": 2,
        "first_observed": "2026-01-01T00:00:00",
        "last_observed": "2026-01-01T00:00:00",
        "occurrences": [],
    }
    base.update(overrides)
    return base


def test_upsert_preserves_first_observed_and_accumulates_count(tmp_path):
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    store.save_citations([make_citation()])
    conn = sqlite3.connect(db)
    original_id = conn.execute("SELECT id FROM citations").fetchone()[0]
    conn.close()

    store.save_citations([make_citation(
        occurrence_count=3,
        first_observed="2026-02-01T00:00:00",
        last_observed="2026-02-01T00:00:00",
    )])

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT id, first_observed, last_observed, occurrence_count FROM citations"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    cid, first, last, count = rows[0]
    assert cid == original_id            # id survives
    assert first == "2026-01-01T00:00:00"  # history preserved
    assert last == "2026-02-01T00:00:00"
    assert count == 5                     # 2 + 3 accumulated


def test_occurrence_rows_written(tmp_path):
    db = str(tmp_path / "t.db")
    seed_analysis(db, "run-1", "an-1", ["https://ex.com/a"])
    store = SQLiteStore(db)
    store.save_citations([make_citation(occurrence_count=1, occurrences=["an-1"])])

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT co.response_analysis_id, c.normalized_url "
        "FROM citation_occurrences co JOIN citations c ON co.citation_id = c.id"
    ).fetchall()
    conn.close()
    assert rows == [("an-1", "https://ex.com/a")]


def test_deduplicator_emits_occurrences(tmp_path):
    db = str(tmp_path / "t.db")
    seed_analysis(db, "run-1", "an-1", ["https://ex.com/a", "https://ex.com/a?utm=x"])
    seed_analysis(db, "run-1", "an-2", ["https://ex.com/a"])
    conn = sqlite3.connect(db)
    citations = CitationDeduplicator(conn).process_citations_from_run("run-1")
    conn.close()
    assert len(citations) == 1
    entry = citations[0]
    assert entry["occurrence_count"] == 3
    assert sorted(entry["occurrences"]) == ["an-1", "an-1", "an-2"]
