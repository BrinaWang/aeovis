"""Tests for rate limiting."""

import time
import pytest
from unittest.mock import patch

from aeo_eval.engine.rate_limiter import RateLimiter, RateLimiterConfig


class TestRateLimiterConfig:
    """Test rate limiter configuration."""

    def test_default_config(self):
        """Test default rate limiter config."""
        config = RateLimiterConfig()
        assert config.tokens_per_minute == 150000
        assert config.requests_per_minute == 100

    def test_custom_config(self):
        """Test custom rate limiter config."""
        config = RateLimiterConfig(
            tokens_per_minute=100000,
            requests_per_minute=50,
        )
        assert config.tokens_per_minute == 100000
        assert config.requests_per_minute == 50


class TestRateLimiter:
    """Test rate limiter behavior."""

    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(
            tpm_limit=150000,
            rpm_limit=100,
        )
        assert limiter.tpm_limit == 150000
        assert limiter.rpm_limit == 100
        assert limiter.tpm_tokens == 150000
        assert limiter.rpm_tokens == 100

    def test_no_wait_when_tokens_available(self):
        """Test that no wait occurs when tokens are available."""
        limiter = RateLimiter(
            tpm_limit=10000,
            rpm_limit=100,
        )

        # Should not wait and should return 0
        wait_time = limiter.wait_for_tokens(
            prompt_tokens=100,
            completion_tokens=100,
        )

        assert wait_time < 0.1  # Minimal wait
        assert limiter.tpm_tokens < 10000  # Tokens consumed

    def test_token_consumption(self):
        """Test that tokens are properly consumed."""
        limiter = RateLimiter(
            tpm_limit=10000,
            rpm_limit=100,
        )

        initial_tpm = limiter.tpm_tokens
        initial_rpm = limiter.rpm_tokens

        limiter.wait_for_tokens(
            prompt_tokens=500,
            completion_tokens=1000,
        )

        # Should have consumed 1500 tokens
        assert limiter.tpm_tokens == initial_tpm - 1500
        # Should have consumed 1 request
        assert limiter.rpm_tokens == initial_rpm - 1

    def test_wait_for_tpm_limit(self):
        """Test waiting when TPM limit would be exceeded."""
        limiter = RateLimiter(
            tpm_limit=10000,
            rpm_limit=1000,
        )

        # Consume most tokens
        limiter.tpm_tokens = 100

        start = time.time()

        # Request that would exceed limit
        limiter.wait_for_tokens(
            prompt_tokens=5000,
            completion_tokens=5000,
        )

        elapsed = time.time() - start

        # Should have waited some time for refill
        # At 60s per minute, 10000 TPM, need to wait for ~9900 tokens
        # Rough estimate: should wait at least 0.5s
        assert elapsed > 0.1  # Some waiting occurred

    def test_status(self):
        """Test rate limiter status."""
        limiter = RateLimiter(
            tpm_limit=150000,
            rpm_limit=100,
        )

        status = limiter.status()

        assert status["tpm_limit"] == 150000
        assert status["rpm_limit"] == 100
        assert "tpm_available" in status
        assert "rpm_available" in status
        assert "tpm_percent" in status
        assert "rpm_percent" in status

    def test_reset(self):
        """Test resetting rate limiter."""
        limiter = RateLimiter(
            tpm_limit=10000,
            rpm_limit=100,
        )

        # Consume tokens
        limiter.wait_for_tokens(100, 100)
        assert limiter.tpm_tokens < 10000

        # Reset
        limiter.reset()
        assert limiter.tpm_tokens == 10000
        assert limiter.rpm_tokens == 100

    def test_multiple_requests(self):
        """Test multiple sequential requests respect rate limits."""
        limiter = RateLimiter(
            tpm_limit=10000,
            rpm_limit=5,
        )

        # Make 3 requests (should fit)
        for i in range(3):
            wait_time = limiter.wait_for_tokens(100, 100)
            assert wait_time < 1.0  # Should be fast

        # Fourth request should have been queued/waited
        # (depending on actual implementation timing)
        remaining_tokens = limiter.tpm_tokens
        assert remaining_tokens < 10000  # Tokens consumed

    def test_rpm_enforcement(self):
        """Test that RPM (requests per minute) is enforced."""
        limiter = RateLimiter(
            tpm_limit=1000000,  # High to not interfere
            rpm_limit=2,  # Only 2 requests per minute
        )

        # First request
        limiter.wait_for_tokens(100, 100)
        assert limiter.rpm_tokens < 2

        # Second request
        limiter.wait_for_tokens(100, 100)
        assert limiter.rpm_tokens < 1

        # Third request would exceed limit
        start = time.time()
        limiter.wait_for_tokens(100, 100)
        elapsed = time.time() - start

        # Should have waited for refill
        assert elapsed > 0.1
