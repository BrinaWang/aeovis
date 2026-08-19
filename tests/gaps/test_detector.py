"""Tests for gap detection."""

import pytest
import sqlite3
from aeo_eval.gaps.detector import GapDetector
from aeo_eval.gaps.thresholds import should_flag_visibility_gap, calculate_gap_priority


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
    """Test gap detector with mock data."""
    conn = sqlite3.connect(":memory:")

    # Create schema
    conn.execute("""
        CREATE TABLE visibility_metrics (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            dimension TEXT,
            dimension_value TEXT,
            striim_mention_rate REAL,
            competitor_mention_rates TEXT,
            num_responses INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE prompts (
            id TEXT PRIMARY KEY,
            prompt_text TEXT,
            topic TEXT,
            persona TEXT,
            intent TEXT,
            priority TEXT
        )
    """)

    # Insert test data
    conn.execute(
        """
        INSERT INTO visibility_metrics VALUES
        ('m1', 'run1', 'by_topic', 'CDC', 0.10, '{"Fivetran": 0.50}', 10)
        """
    )
    conn.execute(
        """
        INSERT INTO prompts (id, prompt_text, topic, persona, intent, priority)
        VALUES ('p1', 'test', 'CDC', 'x', 'y', 'medium')
        """
    )
    conn.commit()

    detector = GapDetector(conn)
    gaps = detector.detect_visibility_gaps("run1")

    assert len(gaps) > 0
    assert gaps[0]["gap_type"] == "visibility"
    assert gaps[0]["priority"] in ["high", "medium", "low"]

    conn.close()
