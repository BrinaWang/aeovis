"""Tests for configuration system."""

import pytest
from aeo_eval.config import Config, RetryPolicyConfig, ProviderConfig, GeneralConfig


class TestRetryPolicyConfig:
    """Test retry policy configuration."""

    def test_default_retry_policy(self):
        """Test default retry policy values."""
        policy = RetryPolicyConfig()
        assert policy.max_retries == 3
        assert policy.initial_delay_ms == 100
        assert policy.backoff_factor == 2.0
        assert policy.max_delay_ms == 30000

    def test_custom_retry_policy(self):
        """Test custom retry policy values."""
        policy = RetryPolicyConfig(
            max_retries=5,
            initial_delay_ms=200,
            backoff_factor=1.5,
        )
        assert policy.max_retries == 5
        assert policy.initial_delay_ms == 200
        assert policy.backoff_factor == 1.5

    def test_retry_policy_validation(self):
        """Test retry policy validation."""
        with pytest.raises(ValueError):
            RetryPolicyConfig(max_retries=0)  # Must be >= 1

        with pytest.raises(ValueError):
            RetryPolicyConfig(initial_delay_ms=5)  # Must be >= 10


class TestProviderConfig:
    """Test provider configuration."""

    def test_default_claude_config(self):
        """Test default Claude configuration."""
        config = ProviderConfig()
        assert config.model_name == "claude-opus-5"
        assert config.rate_limit_tpm == 150000
        assert config.rate_limit_rpm == 100
        assert config.timeout_seconds == 60

    def test_provider_config_with_api_key(self):
        """Test provider config with API key."""
        config = ProviderConfig(
            api_key="sk-ant-test",
            model_name="claude-opus-5",
        )
        assert config.api_key == "sk-ant-test"
        assert config.model_name == "claude-opus-5"

    def test_provider_cost_calculation(self):
        """Test provider cost calculation."""
        config = ProviderConfig(
            cost_per_1k_input_tokens=0.003,
            cost_per_1k_output_tokens=0.015,
        )
        # Cost = (input_tokens / 1000) * cost_per_1k_input + (output_tokens / 1000) * cost_per_1k_output
        # Cost = (1000 / 1000) * 0.003 + (1000 / 1000) * 0.015 = 0.003 + 0.015 = 0.018
        assert config.cost_per_1k_input_tokens == 0.003
        assert config.cost_per_1k_output_tokens == 0.015


class TestGeneralConfig:
    """Test general configuration."""

    def test_default_general_config(self):
        """Test default general configuration."""
        config = GeneralConfig()
        assert config.cost_limit_per_run == 35.0
        assert config.log_level == "INFO"

    def test_custom_general_config(self):
        """Test custom general configuration."""
        config = GeneralConfig(
            cost_limit_per_run=50.0,
            log_level="DEBUG",
        )
        assert config.cost_limit_per_run == 50.0
        assert config.log_level == "DEBUG"

    def test_cost_limit_validation(self):
        """Test cost limit validation (must be > 0)."""
        with pytest.raises(ValueError):
            GeneralConfig(cost_limit_per_run=0)

        with pytest.raises(ValueError):
            GeneralConfig(cost_limit_per_run=-10.0)


class TestRootConfig:
    """Test root configuration object."""

    def test_default_config(self):
        """Test default configuration."""
        config = Config()
        assert "claude" in config.providers
        assert "openai" in config.providers
        assert config.general.cost_limit_per_run == 35.0
        assert len(config.evaluation.competitors) == 6

    def test_config_providers(self):
        """Test provider configurations."""
        config = Config()
        assert config.providers["claude"].model_name == "claude-opus-5"
        assert config.providers["openai"].model_name == "gpt-4o"
        assert config.providers["gemini"].model_name == "gemini-2.0-flash"

    def test_config_evaluation_section(self):
        """Test evaluation configuration section."""
        config = Config()
        assert "Fivetran" in config.evaluation.competitors
        assert "Oracle GoldenGate" in config.evaluation.competitors
        assert len(config.evaluation.crawlers) >= 5

    def test_config_scheduling_section(self):
        """Test scheduling configuration section."""
        config = Config()
        assert config.scheduling.timezone == "US/Eastern"
        assert "0 9 * * MON" in config.scheduling.default_schedule
