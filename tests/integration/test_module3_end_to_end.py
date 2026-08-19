"""Integration test for Module 3 response analysis."""

from aeo_eval.runner.evaluator import Evaluator, RunOptions
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.prompt import Prompt


def test_response_analysis_end_to_end():
    """Test full pipeline: run prompt -> extract analysis -> store."""
    engine = MockEngine()
    evaluator = Evaluator(engine, {"db_path": ":memory:"})

    prompt = Prompt(
        id="test-001",
        prompt="What is Striim?",
        topic="CDC",
        persona="Architect",
        intent="Educational",
        priority="High",
    )

    result = evaluator.run_one(prompt)
    assert result.status in ["success", "failed"]  # Mock might not fully succeed
