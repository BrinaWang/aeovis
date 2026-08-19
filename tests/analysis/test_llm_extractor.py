"""Tests for LLM-based extraction."""

import pytest
from aeo_eval.analysis.llm_extractor import build_extraction_prompt, extract_with_claude
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.models.analysis import StructuredCallResult


def test_build_extraction_prompt():
    """Test that prompt builder produces valid prompt."""
    prompt = build_extraction_prompt(
        "Striim is great for CDC",
        ["Fivetran", "Confluent"]
    )
    assert "Striim" in prompt
    assert "Fivetran" in prompt
    assert "Confluent" in prompt


def test_extract_with_mock_engine():
    """Test extraction with mock engine (returns dummy data)."""
    engine = MockEngine()
    result, cost = extract_with_claude(
        engine,
        "Fivetran is the best tool",
        ["Fivetran", "Striim"]
    )
    # Mock engine does not support structured output; ensure graceful handling
    assert result is None or hasattr(result, "extraction_confidence")
    assert cost == 0.0


class UnparsedJSONEngine(MockEngine):
    """Simulates a structured call whose upstream JSON parse failed: the
    engine falls back to {"raw_response": <text>} instead of raising."""

    def run_with_structured_output(self, prompt_text, schema):
        return StructuredCallResult(data={"raw_response": "garbage"}, cost=0.01)


def test_extract_with_claude_flags_unparsed_response():
    """When the structured call's JSON parse failed upstream, call.data is
    {"raw_response": ...} with none of the expected extraction keys. The
    result must be flagged for review with zero confidence rather than
    silently returned as an unflagged, all-defaults "clean" extraction."""
    engine = UnparsedJSONEngine()
    result, cost = extract_with_claude(
        engine,
        "Fivetran is the best tool",
        ["Fivetran", "Striim"],
    )

    assert result is not None
    assert result.extraction_confidence == 0.0
    assert result.flagged_for_review is True
    # Cost of the call is still tracked even though extraction failed.
    assert cost == 0.01
