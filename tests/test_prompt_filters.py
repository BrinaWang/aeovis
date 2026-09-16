"""Run-option filters must not depend on the casing of the dataset's priority."""
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator, RunOptions


def make_prompts():
    return [
        Prompt(id="p-high", prompt="q", topic="T", persona="x", intent="y", priority="high"),
        Prompt(id="p-low", prompt="q", topic="T", persona="x", intent="y", priority="low"),
    ]


def test_priority_filter_is_case_insensitive(tmp_path):
    """The CLI offers 'High' while question.json stores 'high'; both must match."""
    evaluator = Evaluator(MockEngine(), {"db_path": str(tmp_path / "t.db")})
    selected = list(evaluator._filter_prompts(make_prompts(), RunOptions(priority="High")))
    assert [p.id for p in selected] == ["p-high"]
