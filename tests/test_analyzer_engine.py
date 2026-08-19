"""Analyzer engine selection and analysis-cost accounting."""
import pytest

from aeo_eval.config import config as app_config
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.analysis import StructuredCallResult
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator

VALID_EXTRACTION = {
    "striim_position": 1,
    "competitors": [],
    "striim_claims": [],
    "general_sentiment_toward_striim": "neutral",
    "extraction_confidence": 0.9,
    "flagged_for_review": False,
}


class AnalyzingMockEngine(MockEngine):
    """Mock engine that also supports structured output with a fixed cost."""

    def run_with_structured_output(self, prompt_text, schema):
        return StructuredCallResult(
            data=dict(VALID_EXTRACTION), input_tokens=400, output_tokens=150, cost=0.005
        )


def make_prompt():
    return Prompt(
        id="p1", prompt="q?", topic="Oracle CDC", persona="CISO",
        intent="Commercial", priority="high",
    )


def test_analyzer_falls_back_to_engine_when_claude_unavailable(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(app_config.providers["claude"], "api_key", None)
    engine = MockEngine()
    evaluator = Evaluator(engine, {"db_path": str(tmp_path / "t.db")})
    assert evaluator.analyzer_engine is engine


def test_analyzer_same_provider_reuses_engine(tmp_path):
    engine = MockEngine()
    evaluator = Evaluator(
        engine, {"db_path": str(tmp_path / "t.db"), "analysis_provider": "mock"}
    )
    assert evaluator.analyzer_engine is engine


def test_analysis_cost_is_tracked(tmp_path):
    engine = AnalyzingMockEngine()
    evaluator = Evaluator(
        engine, {"db_path": str(tmp_path / "t.db"), "analysis_provider": "mock"}
    )
    evaluator.run_one(make_prompt())
    # MockEngine sets no actual_cost, so all tracked spend is analysis spend.
    assert evaluator.cost_tracker.spent == pytest.approx(0.005)
