"""Batch totals must land in the evaluation_runs table."""
import sqlite3

import pytest

from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.analysis import StructuredCallResult
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator

# Same shape as tests/test_analyzer_engine.py's VALID_EXTRACTION.
VALID_EXTRACTION = {
    "striim_position": 1,
    "competitors": [],
    "striim_claims": [],
    "general_sentiment_toward_striim": "neutral",
    "extraction_confidence": 0.9,
    "flagged_for_review": False,
}


class CostedEngine(MockEngine):
    def run(self, prompt_text):
        result = super().run(prompt_text)
        result.actual_cost = 0.02
        result.input_tokens = 100
        result.output_tokens = 200
        return result


class CostedAnalyzingEngine(CostedEngine):
    """Also supports structured output, so analysis spend is tracked too."""

    def run_with_structured_output(self, prompt_text, schema):
        return StructuredCallResult(data=dict(VALID_EXTRACTION), cost=0.005)


def make_prompt(pid):
    return Prompt(
        id=pid, prompt="q?", topic="Oracle CDC", persona="CISO",
        intent="Commercial", priority="high",
    )


def test_evaluation_run_totals_persisted(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(CostedEngine(), {"db_path": db})
    evaluator.run_batch([make_prompt("p1"), make_prompt("p2")])

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT num_prompts, cost, status, duration_seconds FROM evaluation_runs WHERE run_id = ?",
        (evaluator.run_batch_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 2
    assert row[1] == pytest.approx(0.04)
    assert row[2] == "completed"
    assert row[3] >= 0


def test_evaluation_run_cost_includes_analyzer_spend(tmp_path):
    """total_cost must reflect the batch-scoped cost_tracker, which also
    records analyzer LLM spend from _extract_and_store_analysis — not
    just the sum of successful results' actual_cost."""
    db = str(tmp_path / "t2.db")
    evaluator = Evaluator(
        CostedAnalyzingEngine(),
        {"db_path": db, "analysis_provider": "mock"},
    )
    evaluator.run_batch([make_prompt("p1"), make_prompt("p2")])

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT cost FROM evaluation_runs WHERE run_id = ?",
        (evaluator.run_batch_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == pytest.approx(2 * 0.02 + 2 * 0.005)
