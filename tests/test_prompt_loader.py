import unittest

from aeo_eval.data.prompt_loader import load_prompts


class PromptLoaderTests(unittest.TestCase):
    def test_prompt_loader_reads_enabled_questions(self):
        prompts = load_prompts("question.json")
        self.assertTrue(prompts)
        self.assertTrue(all(p.enabled for p in prompts))
        self.assertTrue(any(p.topic == "Oracle CDC" for p in prompts))
