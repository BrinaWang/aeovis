"""Tests for retry logic."""

import time
import pytest
from unittest.mock import Mock, patch

from aeo_eval.engine.retry import RetryPolicy, RetryManager


class TestRetryPolicy:
    """Test retry policy configuration and error classification."""

    def test_default_retry_policy(self):
        """Test default retry policy."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.initial_delay_ms == 100
        assert policy.backoff_factor == 2.0

    def test_retryable_exceptions(self):
        """Test that retryable exceptions are identified correctly."""
        policy = RetryPolicy()

        # These should be retryable
        assert policy.should_retry(TimeoutError("timeout"))
        assert policy.should_retry(ConnectionError("connection failed"))
        assert policy.should_retry(IOError("io error"))

    def test_non_retryable_exceptions(self):
        """Test that non-retryable exceptions are identified correctly."""
        policy = RetryPolicy()

        # These should NOT be retryable
        assert not policy.should_retry(ValueError("invalid value"))
        assert not policy.should_retry(KeyError("missing key"))
        assert not policy.should_retry(AttributeError("no attribute"))
        assert not policy.should_retry(TypeError("wrong type"))

    def test_get_delay_calculation(self):
        """Test exponential backoff delay calculation."""
        policy = RetryPolicy(
            initial_delay_ms=100,
            backoff_factor=2.0,
        )

        # First retry: 100ms
        delay_1 = policy.get_delay_ms(1)
        assert 90 <= delay_1 <= 110  # Allow for jitter

        # Second retry: 200ms
        delay_2 = policy.get_delay_ms(2)
        assert 180 <= delay_2 <= 220  # Allow for jitter

        # Third retry: 400ms
        delay_3 = policy.get_delay_ms(3)
        assert 360 <= delay_3 <= 440  # Allow for jitter

    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay_ms."""
        policy = RetryPolicy(
            initial_delay_ms=100,
            backoff_factor=2.0,
            max_delay_ms=1000,
        )

        # Many retries should cap at max_delay
        for attempt in range(10):
            delay = policy.get_delay_ms(attempt)
            assert delay <= policy.max_delay_ms


class TestRetryManager:
    """Test retry manager execution."""

    def test_success_on_first_try(self):
        """Test successful function call on first try."""
        manager = RetryManager()
        fn = Mock(return_value="success")

        result = manager.retry(fn, args=("arg1",), kwargs={"key": "value"})

        assert result == "success"
        fn.assert_called_once_with("arg1", key="value")

    def test_retry_on_transient_error(self):
        """Test retry on transient error."""
        manager = RetryManager()

        # Function fails twice, succeeds on third try
        fn = Mock(side_effect=[
            TimeoutError("timeout"),
            ConnectionError("connection failed"),
            "success",
        ])

        result = manager.retry(fn)

        assert result == "success"
        assert fn.call_count == 3

    def test_fail_on_permanent_error(self):
        """Test immediate failure on non-retryable error."""
        manager = RetryManager()

        # ValueError is not retryable
        fn = Mock(side_effect=ValueError("bad input"))

        with pytest.raises(ValueError):
            manager.retry(fn)

        # Should only try once
        assert fn.call_count == 1

    def test_max_retries_exceeded(self):
        """Test failure when max retries exceeded."""
        policy = RetryPolicy(max_retries=2)
        manager = RetryManager(policy)

        # Always fail with retryable error
        fn = Mock(side_effect=TimeoutError("timeout"))

        with pytest.raises(TimeoutError):
            manager.retry(fn)

        # Should try initial + 2 retries = 3 times
        assert fn.call_count == 3

    @patch("time.sleep")
    def test_exponential_backoff_timing(self, mock_sleep):
        """Test that backoff delays are applied."""
        policy = RetryPolicy(
            max_retries=3,
            initial_delay_ms=100,
            backoff_factor=2.0,
        )
        manager = RetryManager(policy)

        # Always fail to trigger retries
        fn = Mock(side_effect=TimeoutError("timeout"))

        with pytest.raises(TimeoutError):
            manager.retry(fn)

        # Should sleep 3 times (retries 1, 2, 3)
        assert mock_sleep.call_count == 3

        # Check approximate delays (in seconds)
        # First retry: ~0.1s, second: ~0.2s, third: ~0.4s
        calls = mock_sleep.call_args_list
        assert calls[0][0][0] < 0.15  # First sleep, some jitter
        assert calls[1][0][0] < 0.25  # Second sleep
        assert calls[2][0][0] < 0.45  # Third sleep

    def test_custom_exceptions(self):
        """Test custom exception handling."""
        custom_retryable = {TimeoutError, IOError}
        policy = RetryPolicy(retryable_exceptions=custom_retryable)
        manager = RetryManager(policy)

        # Custom error should be retryable
        fn = Mock(side_effect=[
            TimeoutError("timeout"),
            "success",
        ])

        result = manager.retry(fn)
        assert result == "success"
        assert fn.call_count == 2
