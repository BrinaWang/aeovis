"""Visibility gap thresholds must use the topic's real priority, any case."""
import sqlite3

from aeo_eval.gaps.detector import GapDetector
from aeo_eval.gaps.thresholds import should_flag_visibility_gap
from aeo_eval.storage.sqlite_store import SQLiteStore


def test_thresholds_are_case_insensitive():
    # 12% is below the High threshold (15%) but above Medium (5%)
    assert should_flag_visibility_gap(0.12, 0.0, "high") is True
    assert should_flag_visibility_gap(0.12, 0.0, "High") is True
    assert should_flag_visibility_gap(0.12, 0.0, "medium") is False


def seed_topic_metrics(db, run_id, topic, priority, mention_rate):
    store = SQLiteStore(db)
    store.init_db()
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT OR IGNORE INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts) "
        "VALUES (?, datetime('now'), 'mock', 'mock-v1', 1)",
        (run_id,),
    )
    conn.execute(
        "INSERT INTO prompts (id, prompt_text, topic, persona, intent, priority) "
        "VALUES (?, 'q', ?, 'x', 'y', ?)",
        (f"p-{topic}", topic, priority),
    )
    conn.commit()
    conn.close()
    store.save_metrics(run_id, {
        "dimension": "by_topic", "dimension_value": topic,
        "mention_rate": mention_rate, "competitor_mention_rates": {},
        "num_responses": 12,
    })


def test_high_priority_topic_uses_high_threshold(tmp_path):
    db = str(tmp_path / "t.db")
    seed_topic_metrics(db, "run-1", "Oracle CDC", "high", 0.12)
    conn = sqlite3.connect(db)
    gaps = GapDetector(conn).detect_visibility_gaps("run-1")
    conn.close()
    assert len(gaps) == 1  # 12% < 15% High threshold


def test_medium_priority_topic_uses_medium_threshold(tmp_path):
    db = str(tmp_path / "t.db")
    seed_topic_metrics(db, "run-1", "Data Replication", "medium", 0.12)
    conn = sqlite3.connect(db)
    gaps = GapDetector(conn).detect_visibility_gaps("run-1")
    conn.close()
    assert gaps == []  # 12% > 5% Medium threshold, no competitor pressure
