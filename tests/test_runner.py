import unittest

from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.prompt import Prompt
from aeo_eval.runner.evaluator import Evaluator


class EvaluatorTests(unittest.TestCase):
    def test_evaluator_runs_prompt(self):
        evaluator = Evaluator(MockEngine())
        prompt = Prompt(
            id="demo-1",
            prompt="Best Oracle CDC tools?",
            topic="Oracle CDC",
            persona="VP of Engineering / CTO",
            intent="commercial",
            priority="high",
        )

        result = evaluator.run_one(prompt)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.prompt_id, "demo-1")
        self.assertIsNotNone(result.response_text)
