import unittest

from aeo_eval.analysis.extractor import extract_brand_mentions


class ExtractorTests(unittest.TestCase):
    def test_extract_brand_mentions_detects_known_names(self):
        text = "Striim offers real-time CDC while Fivetran and Oracle GoldenGate are alternatives."
        brands = extract_brand_mentions(text)

        self.assertIn("Striim", brands)
        self.assertIn("Fivetran", brands)
        self.assertIn("Oracle GoldenGate", brands)
