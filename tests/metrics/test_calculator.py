"""Tests for metrics calculation."""

import pytest
import sqlite3
from aeo_eval.metrics.calculator import MetricsCalculator


def test_metrics_calculation():
    """Test basic metrics calculation."""
    # Setup in-memory DB
    conn = sqlite3.connect(":memory:")

    # Create minimal schema (stripped down for testing)
    conn.execute("""
        CREATE TABLE response_analysis (
            id TEXT PRIMARY KEY,
            raw_response_id TEXT,
            striim_mentioned INTEGER,
            striim_recommended INTEGER,
            striim_position INTEGER,
            brands_found TEXT,
            citations TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE raw_responses (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            prompt_id TEXT
        )
    """)

    # Insert test data
    conn.execute("INSERT INTO raw_responses VALUES ('r1', 'run1', 'p1')")
    conn.execute("INSERT INTO response_analysis VALUES ('a1', 'r1', 1, 0, 2, '[]', '[]')")
    conn.commit()

    # Calculate metrics
    calc = MetricsCalculator(conn)
    metrics = calc.calculate_metrics_for_run("run1")

    assert metrics["mention_rate"] == 1.0
    assert metrics["num_responses"] == 1
    assert metrics["top3_rate"] == 1.0
    assert metrics["avg_position"] == 2.0

    conn.close()


def test_metrics_with_missing_run():
    """Test graceful handling of missing run."""
    conn = sqlite3.connect(":memory:")

    # Create minimal schema
    conn.execute("""
        CREATE TABLE response_analysis (
            id TEXT PRIMARY KEY,
            raw_response_id TEXT,
            striim_mentioned INTEGER,
            striim_recommended INTEGER,
            striim_position INTEGER,
            brands_found TEXT,
            citations TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE raw_responses (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            prompt_id TEXT
        )
    """)
    conn.commit()

    calc = MetricsCalculator(conn)
    metrics = calc.calculate_metrics_for_run("nonexistent")

    assert metrics == {}  # Empty dict when no data found

    conn.close()
