"""Tests for gap detection."""

import json
import pytest
import sqlite3
from pathlib import Path
from aeo_eval.gaps.detector import GapDetector
from aeo_eval.gaps.thresholds import should_flag_visibility_gap, calculate_gap_priority

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "aeo_eval" / "storage" / "sqlite_schema.sql"


def _full_schema_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts)"
        " VALUES ('run1', '2026-09-16T00:00:00', 'mock', 'mock-v1', 3)"
    )
    for pid in ("p-missed-1", "p-missed-2", "p-hit"):
        conn.execute(
            "INSERT INTO prompts (id, prompt_text, topic, persona, intent, priority)"
            " VALUES (?, 'q', 'CDC', 'x', 'y', 'high')",
            (pid,),
        )
        conn.execute(
            "INSERT INTO raw_responses (id, run_id, prompt_id, engine, status)"
            " VALUES (?, 'run1', ?, 'mock', 'success')",
            (f"r-{pid}", pid),
        )
        conn.execute(
            "INSERT INTO response_analysis (id, raw_response_id, striim_mentioned, citations)"
            " VALUES (?, ?, ?, ?)",
            (f"a-{pid}", f"r-{pid}", 0 if pid.startswith("p-missed") else 1,
             json.dumps(["https://www.fivetran.com/docs/oracle"])),
        )
    return conn


def test_visibility_gap_lists_prompts_where_striim_was_not_mentioned():
    conn = _full_schema_conn()
    conn.execute(
        "INSERT INTO visibility_metrics (id, run_id, dimension, dimension_value,"
        " striim_mention_rate, competitor_mention_rates, num_responses)"
        " VALUES ('m1', 'run1', 'by_topic', 'CDC', 0.05, '{\"Fivetran\": 0.9}', 3)"
    )
    conn.commit()

    gaps = GapDetector(conn).detect_visibility_gaps("run1")

    assert len(gaps) == 1
    assert sorted(gaps[0]["affected_prompts"]) == ["p-missed-1", "p-missed-2"]


def test_citation_gap_lists_every_prompt_in_the_topic():
    conn = _full_schema_conn()
    conn.execute(
        "INSERT INTO citations (id, url, normalized_url, domain, source_category,"
        " first_observed, last_observed) VALUES ('c1', 'u', 'https://www.fivetran.com/docs/oracle',"
        " 'www.fivetran.com', 'competitor', '2026-09-16', '2026-09-16')"
    )
    for pid in ("p-missed-1", "p-missed-2", "p-hit"):
        conn.execute(
            "INSERT INTO citation_occurrences (id, citation_id, response_analysis_id)"
            " VALUES (?, 'c1', ?)",
            (f"o-{pid}", f"a-{pid}"),
        )
    conn.commit()

    gaps = GapDetector(conn).detect_citation_gaps("run1")

    assert len(gaps) == 1
    assert sorted(gaps[0]["affected_prompts"]) == ["p-hit", "p-missed-1", "p-missed-2"]


def test_should_flag_visibility_gap():
    """Test visibility gap detection logic."""
    assert should_flag_visibility_gap(0.10, 0.50, "High") is True  # Below threshold
    assert should_flag_visibility_gap(0.10, 0.25, "High") is True   # 2.5x disadvantage
    assert should_flag_visibility_gap(0.30, 0.40, "High") is False  # Above threshold


def test_calculate_gap_priority():
    """Test gap priority calculation."""
    assert calculate_gap_priority(0.10, 0.40) == "high"    # 3x gap
    assert calculate_gap_priority(0.10, 0.26) == "medium"  # gap_ratio 1.6 (avoids float boundary at exactly 1.5)
    assert calculate_gap_priority(0.10, 0.15) == "low"     # 1.5x gap


def test_gap_detector_visibility_gaps():
    """Test gap detector with mock data on the real schema."""
    conn = _full_schema_conn()
    conn.execute(
        "INSERT INTO visibility_metrics (id, run_id, dimension, dimension_value,"
        " striim_mention_rate, competitor_mention_rates, num_responses)"
        " VALUES ('m1', 'run1', 'by_topic', 'CDC', 0.10, '{\"Fivetran\": 0.50}', 10)"
    )
    conn.commit()

    detector = GapDetector(conn)
    gaps = detector.detect_visibility_gaps("run1")

    assert len(gaps) > 0
    assert gaps[0]["gap_type"] == "visibility"
    assert gaps[0]["priority"] in ["high", "medium", "low"]

    conn.close()
