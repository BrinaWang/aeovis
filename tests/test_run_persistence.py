"""Every engine result — including failures — must be persisted."""
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator, RunOptions
from aeo_eval.storage.sqlite_store import SQLiteStore


class FailingEngine(MockEngine):
    def run(self, prompt_text):
        result = super().run(prompt_text)
        result.status = "failed"
        result.response_text = None
        result.error = "boom"
        return result


class ExpensiveEngine(MockEngine):
    """Succeeds, but its actual_cost trips the batch cost limit."""

    def run(self, prompt_text):
        result = super().run(prompt_text)
        result.actual_cost = 5.0
        return result


def make_prompt(pid="p1"):
    return Prompt(
        id=pid, prompt="q?", topic="Oracle CDC", persona="CISO",
        intent="Commercial", priority="high",
    )


def test_failed_result_is_persisted(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(FailingEngine(), {"db_path": db})
    evaluator.run_one(make_prompt())
    rows = SQLiteStore(db).get_raw_responses_by_batch(evaluator.run_batch_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["error"] == "boom"


def test_successful_result_is_persisted_exactly_once(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(MockEngine(), {"db_path": db})
    evaluator.run_one(make_prompt())
    rows = SQLiteStore(db).get_raw_responses_by_batch(evaluator.run_batch_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"


def test_dry_run_is_not_persisted(tmp_path):
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(MockEngine(), {"db_path": db})
    evaluator.run_one(make_prompt(), RunOptions(dry_run=True))
    assert SQLiteStore(db).get_raw_responses_by_batch(evaluator.run_batch_id) == []


def test_cost_limit_trip_does_not_double_persist_the_tripping_prompt(tmp_path):
    """run_one already persists the real (successful) result for the prompt
    whose cost trips the batch limit. The synthetic cost_limit_exceeded
    bookkeeping row that run_batch appends to `results` must not also be
    written to raw_responses, or the prompt gets double-counted."""
    db = str(tmp_path / "t.db")
    evaluator = Evaluator(
        ExpensiveEngine(), {"db_path": db, "cost_limit_per_run": 1.0}
    )
    evaluator.run_batch([make_prompt("p1")])

    rows = SQLiteStore(db).get_raw_responses_by_batch(evaluator.run_batch_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
