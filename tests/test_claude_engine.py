"""Tests for Claude engine."""

import time

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from aeo_eval.engine.claude_engine import ClaudeEngine
from aeo_eval.models.result import RunResult


@pytest.fixture
def claude_config():
    """Provide test configuration for Claude engine."""
    return {
        "api_key": "sk-ant-test",
        "model_name": "claude-opus-5",
        "rate_limit_tpm": 150000,
        "rate_limit_rpm": 100,
        "timeout_seconds": 60,
        "cost_per_1k_input_tokens": 0.003,
        "cost_per_1k_output_tokens": 0.015,
    }


class TestClaudeEngineInitialization:
    """Test Claude engine initialization."""

    def test_initialization_with_config(self, claude_config):
        """Test engine initialization with configuration."""
        with patch("anthropic.Anthropic"):
            engine = ClaudeEngine(claude_config)
            assert engine.name == "claude"
            assert engine.model_name == "claude-opus-5"
            assert engine.timeout == 60

    def test_initialization_without_api_key(self):
        """Test that initialization fails without API key."""
        config = {"model_name": "claude-opus-5"}

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY required"):
            ClaudeEngine(config)

    def test_get_token_costs(self, claude_config):
        """Test token cost retrieval."""
        with patch("anthropic.Anthropic"):
            engine = ClaudeEngine(claude_config)
            costs = engine.get_token_costs()

            assert costs["input"] == 0.003
            assert costs["output"] == 0.015

    def test_estimate_cost(self, claude_config):
        """Test cost estimation."""
        with patch("anthropic.Anthropic"):
            engine = ClaudeEngine(claude_config)
            cost = engine.estimate_cost(
                prompt_tokens=1000,
                completion_tokens=1000,
            )

            # (1000/1000)*0.003 + (1000/1000)*0.015 = 0.018
            assert cost == pytest.approx(0.018, abs=0.001)


class TestClaudeEngineRun:
    """Test Claude engine run method."""

    def test_successful_run(self, claude_config):
        """Test successful prompt run."""
        engine = ClaudeEngine(claude_config)
        engine.client = MagicMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is the response")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        engine.client.messages.create.return_value = mock_response

        result = engine.run("What is 2+2?")

        assert result.status == "success"
        assert result.response_text == "This is the response"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        # (100/1000)*0.003 + (50/1000)*0.015 = 0.00105
        assert result.actual_cost == pytest.approx(0.00105, abs=0.0001)

    def test_run_with_empty_response(self, claude_config):
        """Test handling of empty response."""
        engine = ClaudeEngine(claude_config)
        engine.client = MagicMock()

        mock_response = MagicMock()
        mock_response.content = []  # Empty content
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 0

        engine.client.messages.create.return_value = mock_response

        result = engine.run("Test prompt")

        assert result.status == "success"
        assert result.response_text == ""

    def test_run_with_timeout(self, claude_config):
        """Test handling of timeout error."""
        import httpx
        from anthropic import APITimeoutError

        engine = ClaudeEngine(claude_config)
        engine.client = MagicMock()
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        engine.client.messages.create.side_effect = APITimeoutError(request)

        result = engine.run("Test prompt")

        assert result.status == "timeout"
        assert result.error is not None
        assert result.response_text is None

    def test_run_with_rate_limit(self, claude_config):
        """Test handling of rate limit error."""
        import httpx
        from anthropic import RateLimitError

        engine = ClaudeEngine(claude_config)
        engine.client = MagicMock()
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(429, request=request)
        engine.client.messages.create.side_effect = RateLimitError(
            "Rate limit exceeded",
            response=response,
            body=None,
        )

        result = engine.run("Test prompt")

        assert result.status == "rate_limited"
        assert result.error is not None

    def test_run_with_api_error(self, claude_config):
        """Test handling of general API error."""
        import httpx
        from anthropic import APIError

        engine = ClaudeEngine(claude_config)
        engine.client = MagicMock()
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        engine.client.messages.create.side_effect = APIError(
            "Server error",
            request=request,
            body=None,
        )

        result = engine.run("Test prompt")

        assert result.status == "failed"
        assert result.error is not None

    def test_run_metadata(self, claude_config):
        """Test that run metadata is properly set."""
        engine = ClaudeEngine(claude_config)
        engine.client = MagicMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        def _create_response(*args, **kwargs):
            # Small delay so latency_ms is measurably > 0
            time.sleep(0.001)
            return mock_response

        engine.client.messages.create.side_effect = _create_response

        result = engine.run("Test")

        assert result.engine == "claude"
        assert result.model == "claude-opus-5"
        assert result.engine_name == "ClaudeEngine"
        assert isinstance(result.run_timestamp, datetime)
        assert result.latency_ms > 0


class TestClaudeEngineRateLimit:
    """Test Claude engine rate limiting."""

    def test_rate_limiter_acquired(self, claude_config):
        """Test that rate limiter is used."""
        engine = ClaudeEngine(claude_config)
        engine.client = MagicMock()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        engine.client.messages.create.return_value = mock_response

        limiter = engine.get_rate_limiter()

        initial_tokens = limiter.tpm_tokens

        result = engine.run("Test")

        # Should have consumed tokens
        assert limiter.tpm_tokens < initial_tokens

    @patch("anthropic.Anthropic")
    def test_get_rate_limiter_config(self, mock_anthropic_class, claude_config):
        """Test rate limiter configuration."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        engine = ClaudeEngine(claude_config)
        config = engine.get_rate_limiter_config()

        assert config.tokens_per_minute == 150000
        assert config.requests_per_minute == 100


class TestClaudeEngineRetry:
    """Test Claude engine retry behavior."""

    @patch("anthropic.Anthropic")
    def test_retry_policy(self, mock_anthropic_class, claude_config):
        """Test retry policy configuration."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        engine = ClaudeEngine(claude_config)
        policy = engine.get_retry_policy()

        assert policy.max_retries == 3
        assert policy.initial_delay_ms == 100

    @patch("anthropic.Anthropic")
    def test_custom_retry_policy(self, mock_anthropic_class):
        """Test custom retry policy from config."""
        config = {
            "api_key": "sk-ant-test",
            "model_name": "claude-opus-5",
            "max_retries": 5,
        }

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        engine = ClaudeEngine(config)
        policy = engine.get_retry_policy()

        assert policy.max_retries == 5
