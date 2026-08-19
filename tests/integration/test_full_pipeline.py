"""Integration test for full pipeline."""

from __future__ import annotations

import sqlite3

from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.prompt import Prompt
from aeo_eval.orchestrator import AEOPipelineOrchestrator


def test_full_pipeline_integration():
    """Test complete pipeline from prompts to recommendations."""
    engine = MockEngine()
    config = {"db_path": ":memory:"}

    orchestrator = AEOPipelineOrchestrator(engine, config)

    prompts = [
        Prompt(
            id="test-001",
            prompt="What is Striim?",
            topic="CDC",
            persona="Architect",
            intent="Educational",
            priority="High",
        ),
    ]

    result = orchestrator.run_full_pipeline(prompts)

    assert "run_id" in result
    assert result["num_prompts"] == 1
    assert result["num_gaps"] >= 0
    assert result["num_recommendations"] >= 0
    assert result["num_auto_approved"] >= 0


def test_full_pipeline_persists_every_stage(tmp_path):
    """Verify every pipeline stage actually wrote rows to storage.

    Uses a real (temp-file) SQLite database, rather than ":memory:", so
    the assertions below can open a fresh connection *after* the pipeline
    finishes and still see everything earlier stages wrote.
    """
    engine = MockEngine()
    db_path = str(tmp_path / "pipeline.db")
    config = {"db_path": db_path}
    orchestrator = AEOPipelineOrchestrator(engine, config)

    prompts = [
        Prompt(
            id=f"test-{i:03d}",
            prompt="What is Striim and how does it compare for Oracle CDC?",
            topic="Oracle CDC",
            persona="Architect",
            intent="Educational",
            priority="High",
        )
        for i in range(3)
    ]

    result = orchestrator.run_full_pipeline(prompts)
    run_id = result["run_id"]

    conn = sqlite3.connect(db_path)
    try:
        # Module 2/3: raw responses + analysis persisted per prompt.
        raw_count = conn.execute(
            "SELECT COUNT(*) FROM raw_responses WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert raw_count == len(prompts)

        analysis_count = conn.execute(
            """
            SELECT COUNT(*) FROM response_analysis ra
            JOIN raw_responses rr ON ra.raw_response_id = rr.id
            WHERE rr.run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]
        assert analysis_count == len(prompts)

        # Module 4: overall visibility metrics were calculated and saved.
        overall_metrics = conn.execute(
            "SELECT COUNT(*) FROM visibility_metrics WHERE run_id = ? AND dimension = 'overall'",
            (run_id,),
        ).fetchone()[0]
        assert overall_metrics == 1
    finally:
        conn.close()
