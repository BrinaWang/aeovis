"""Module 3 must detect the competitors configured in config.yaml, not a hardcoded list."""
import json

from aeo_eval.config import config as app_config
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.analysis import StructuredCallResult
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator
from aeo_eval.storage.sqlite_store import SQLiteStore

VALID_EXTRACTION = {
    "striim_position": None,
    "competitors": [],
    "striim_claims": [],
    "general_sentiment_toward_striim": "neutral",
    "extraction_confidence": 0.9,
    "flagged_for_review": False,
}


class QlikMentioningEngine(MockEngine):
    def run(self, prompt_text):
        result = super().run(prompt_text)
        result.response_text = "For CDC many teams pick Qlik Replicate or Estuary Flow."
        return result

    def run_with_structured_output(self, prompt_text, schema):
        return StructuredCallResult(data=dict(VALID_EXTRACTION), cost=0.0)


def test_configured_competitors_are_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config.evaluation, "competitors", ["Qlik Replicate", "Estuary"])
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(QlikMentioningEngine(), {"db_path": db, "analysis_provider": "mock"})
    evaluator.run_one(
        Prompt(id="p1", prompt="q?", topic="CDC", persona="x", intent="y", priority="high")
    )
    rows = SQLiteStore(db).get_analysis_by_batch(evaluator.run_batch_id)
    assert len(rows) == 1
    brands = json.loads(rows[0]["brands_found"])
    assert "Qlik Replicate" in brands
    assert "Estuary" in brands
