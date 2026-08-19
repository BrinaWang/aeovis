"""Citation gaps must be run-scoped and topic-based."""
import json
import sqlite3
import uuid

from aeo_eval.gaps.detector import GapDetector
from aeo_eval.storage.sqlite_store import SQLiteStore


def seed(conn, run_id, topic, analysis_id, cited_domains):
    """Seed one analyzed response in `topic` citing `cited_domains`.

    cited_domains: list of (domain, source_category) tuples.
    """
    prompt_id = f"prompt-{topic}-{analysis_id}"
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
        "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, striim_recommended, citations) "
        "VALUES (?, ?, 1, 0, ?)",
        (analysis_id, rr_id, json.dumps([])),
    )
    for domain, category in cited_domains:
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


def make_db(tmp_path):
    db = str(tmp_path / "t.db")
    SQLiteStore(db).init_db()
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_flags_topic_with_competitor_citations_and_no_striim(tmp_path):
    conn = make_db(tmp_path)
    seed(conn, "run-1", "Oracle CDC", "an-1",
         [("fivetran.com", "competitor"), ("fivetran.com", "competitor"),
          ("qlik.com", "competitor")])
    gaps = GapDetector(conn).detect_citation_gaps("run-1")
    assert len(gaps) == 1
    assert gaps[0]["topic"] == "Oracle CDC"
    assert gaps[0]["gap_type"] == "citation"


def test_topic_with_striim_citation_not_flagged(tmp_path):
    conn = make_db(tmp_path)
    seed(conn, "run-1", "Oracle CDC", "an-1",
         [("fivetran.com", "competitor"), ("fivetran.com", "competitor"),
          ("qlik.com", "competitor"), ("striim.com", "striim_owned")])
    assert GapDetector(conn).detect_citation_gaps("run-1") == []


def test_other_runs_do_not_leak_in(tmp_path):
    conn = make_db(tmp_path)
    # 3 competitor citations, but in a DIFFERENT run
    seed(conn, "run-0", "Oracle CDC", "an-old",
         [("fivetran.com", "competitor"), ("fivetran.com", "competitor"),
          ("qlik.com", "competitor")])
    seed(conn, "run-1", "Oracle CDC", "an-new", [("fivetran.com", "competitor")])
    assert GapDetector(conn).detect_citation_gaps("run-1") == []
