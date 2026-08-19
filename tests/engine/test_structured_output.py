"""Structured output must be schema-enforced, rate-limited, and report usage."""
import json
from unittest.mock import MagicMock

from aeo_eval.engine.claude_engine import ClaudeEngine
from aeo_eval.models.analysis import StructuredCallResult

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"x": {"type": "integer"}}, "required": ["x"]}


def make_engine():
    engine = ClaudeEngine({"api_key": "test-key"})
    engine.client = MagicMock()
    text_block = MagicMock()
    text_block.text = json.dumps({"x": 2})
    message = MagicMock()
    message.content = [text_block]
    message.usage.input_tokens = 500
    message.usage.output_tokens = 100
    engine.client.messages.create.return_value = message
    return engine


def test_claude_structured_call_uses_output_config_and_no_temperature():
    engine = make_engine()
    engine.run_with_structured_output("analyze this", SCHEMA)
    kwargs = engine.client.messages.create.call_args.kwargs
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA}
    }
    assert "temperature" not in kwargs


def test_claude_run_does_not_send_temperature():
    engine = make_engine()
    engine.run("hello")
    kwargs = engine.client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs


def test_structured_call_returns_usage_and_cost():
    engine = make_engine()
    result = engine.run_with_structured_output("analyze this", SCHEMA)
    assert isinstance(result, StructuredCallResult)
    assert result.data == {"x": 2}
    assert result.input_tokens == 500
    assert result.output_tokens == 100
    # 500/1000 * 0.003 + 100/1000 * 0.015 = 0.0015 + 0.0015
    assert abs(result.cost - 0.003) < 1e-9
