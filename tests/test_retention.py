"""Retention policy must actually delete expired rows, FK-safely."""
import json
import sqlite3
import uuid

from aeo_eval.storage.sqlite_store import SQLiteStore

OLD = "2020-01-01 00:00:00"  # far beyond every retention window


def seed(conn, run_id, analysis_id, created_at, with_citation=True):
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    rr_id = f"rr-{analysis_id}"
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine, created_at) "
        "VALUES (?, ?, 'p1', 'mock', ?)",
        (rr_id, run_id, created_at),
    )
    conn.execute(
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, "
        "striim_recommended, citations, created_at) VALUES (?, ?, 1, 0, ?, ?)",
        (analysis_id, rr_id, json.dumps([]), created_at),
    )
    if with_citation:
        cit_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO citations (id, url, normalized_url, domain, source_category, "
            "first_observed, last_observed, occurrence_count, created_at) "
            "VALUES (?, 'https://ex.com/a', ?, 'ex.com', 'other', ?, ?, 1, ?)",
            (cit_id, f"https://ex.com/{analysis_id}", created_at, created_at, created_at),
        )
        conn.execute(
            "INSERT INTO citation_occurrences (id, citation_id, response_analysis_id) "
            "VALUES (?, ?, ?)",
            (str(uuid.uuid4()), cit_id, analysis_id),
        )
    conn.commit()


def counts(conn):
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("raw_responses", "response_analysis", "citations",
                      "citation_occurrences")
    }


def test_expired_rows_deleted_fresh_rows_kept(tmp_path):
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    seed(conn, "run-old", "an-old", OLD)
    fresh = conn.execute("SELECT datetime('now')").fetchone()[0]
    seed(conn, "run-new", "an-new", fresh)
    conn.close()

    deleted = store.apply_retention()

    conn = sqlite3.connect(db)
    remaining = counts(conn)
    conn.close()
    assert remaining == {
        "raw_responses": 1, "response_analysis": 1,
        "citations": 1, "citation_occurrences": 1,
    }
    assert deleted["raw_responses"] == 1
    assert deleted["response_analysis"] == 1


def test_apply_retention_is_idempotent_on_empty_db(tmp_path):
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    assert all(v == 0 for v in store.apply_retention().values())


def test_continuously_cited_page_survives_on_recent_last_observed(tmp_path):
    """The Task-5 upsert (save_citations) deliberately never refreshes
    created_at on repeat citations — only last_observed and
    occurrence_count. A citation must therefore be purged by
    last_observed, not created_at, or a continuously-cited page (and its
    RECENT citation_occurrences rows) would be deleted at the created_at
    retention boundary even though it was cited again yesterday."""
    db = str(tmp_path / "t.db")
    store = SQLiteStore(db)
    store.init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    # response_analysis/raw_responses stay fresh so only the citations
    # table's own retention window is under test here.
    fresh = conn.execute("SELECT datetime('now')").fetchone()[0]
    seed(conn, "run-recent", "an-recent", fresh, with_citation=False)

    # Citation row itself has an old created_at (first ever seen long
    # ago) but a recent last_observed (cited again recently).
    cit_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO citations (id, url, normalized_url, domain, source_category, "
        "first_observed, last_observed, occurrence_count, created_at) "
        "VALUES (?, 'https://ex.com/a', ?, 'ex.com', 'other', ?, ?, 5, ?)",
        (cit_id, "https://ex.com/an-recent", OLD, fresh, OLD),
    )
    conn.execute(
        "INSERT INTO citation_occurrences (id, citation_id, response_analysis_id) "
        "VALUES (?, ?, ?)",
        (str(uuid.uuid4()), cit_id, "an-recent"),
    )
    conn.commit()
    conn.close()

    store.apply_retention()

    conn = sqlite3.connect(db)
    citation_count = conn.execute(
        "SELECT COUNT(*) FROM citations WHERE id = ?", (cit_id,)
    ).fetchone()[0]
    occurrence_count = conn.execute(
        "SELECT COUNT(*) FROM citation_occurrences WHERE citation_id = ?", (cit_id,)
    ).fetchone()[0]
    conn.close()

    assert citation_count == 1
    assert occurrence_count == 1
