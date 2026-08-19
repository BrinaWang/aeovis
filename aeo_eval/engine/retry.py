"""Retry logic for handling transient failures in API calls."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Callable, Optional, Set, TypeVar

from anthropic import APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """Configuration for retry behavior with exponential backoff."""
    max_retries: int = 3
    initial_delay_ms: int = 100
    backoff_factor: float = 2.0
    max_delay_ms: int = 30000
    retryable_exceptions: Set[type] = None  # Default set below
    non_retryable_exceptions: Set[type] = None  # Default set below

    def __post_init__(self):
        """Initialize default exception sets."""
        if self.retryable_exceptions is None:
            self.retryable_exceptions = {
                APITimeoutError,
                RateLimitError,
                TimeoutError,
                ConnectionError,
                IOError,
            }
        if self.non_retryable_exceptions is None:
            self.non_retryable_exceptions = {
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
                AssertionError,
            }

    def should_retry(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        # Check explicit lists first
        if type(error) in self.non_retryable_exceptions:
            return False
        if type(error) in self.retryable_exceptions:
            return True

        # Check by inheritance (handles subclasses)
        if any(isinstance(error, exc) for exc in self.non_retryable_exceptions):
            return False
        if any(isinstance(error, exc) for exc in self.retryable_exceptions):
            return True

        # Default: retry on unknown errors (safe for transient failures)
        return True

    def get_delay_ms(self, attempt: int) -> int:
        """Calculate delay for a given retry attempt with jitter."""
        if attempt <= 0:
            return 0

        delay = self.initial_delay_ms * (self.backoff_factor ** (attempt - 1))
        delay = min(delay, self.max_delay_ms)

        # Add jitter (±10%) to avoid thundering herd
        jitter = delay * 0.1 * (2 * random.random() - 1)
        delay = max(0, delay + jitter)
        delay = min(delay, self.max_delay_ms)

        return int(delay)


class RetryManager:
    """Manages retry logic with exponential backoff."""

    def __init__(self, policy: Optional[RetryPolicy] = None):
        """Initialize with optional custom retry policy."""
        self.policy = policy or RetryPolicy()

    def retry(
        self,
        fn: Callable[..., T],
        args: tuple = (),
        kwargs: Optional[dict] = None,
    ) -> T:
        """
        Execute a function with retry logic.

        Args:
            fn: Function to call
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Result of fn()

        Raises:
            The last exception encountered after max retries exhausted
        """
        kwargs = kwargs or {}
        last_error: Optional[Exception] = None
        errors: list[Exception] = []

        for attempt in range(self.policy.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                errors.append(e)

                if not self.policy.should_retry(e):
                    logger.error(f"Non-retryable error: {type(e).__name__}: {e}")
                    raise

                if attempt < self.policy.max_retries:
                    delay_ms = self.policy.get_delay_ms(attempt + 1)
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.policy.max_retries} failed: "
                        f"{type(e).__name__}: {e}. Retrying in {delay_ms}ms..."
                    )
                    import time
                    time.sleep(delay_ms / 1000.0)
                else:
                    logger.error(
                        f"Max retries ({self.policy.max_retries}) exhausted. "
                        f"Last error: {type(e).__name__}: {e}"
                    )

        if last_error:
            raise last_error

    async def retry_async(
        self,
        fn: Callable[..., Any],
        args: tuple = (),
        kwargs: Optional[dict] = None,
    ) -> T:
        """
        Execute an async function with retry logic.

        Args:
            fn: Async function to call
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Result of fn()

        Raises:
            The last exception encountered after max retries exhausted
        """
        kwargs = kwargs or {}
        last_error: Optional[Exception] = None
        errors: list[Exception] = []

        for attempt in range(self.policy.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                errors.append(e)

                if not self.policy.should_retry(e):
                    logger.error(f"Non-retryable error: {type(e).__name__}: {e}")
                    raise

                if attempt < self.policy.max_retries:
                    delay_ms = self.policy.get_delay_ms(attempt + 1)
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.policy.max_retries} failed: "
                        f"{type(e).__name__}: {e}. Retrying in {delay_ms}ms..."
                    )
                    await asyncio.sleep(delay_ms / 1000.0)
                else:
                    logger.error(
                        f"Max retries ({self.policy.max_retries}) exhausted. "
                        f"Last error: {type(e).__name__}: {e}"
                    )

        if last_error:
            raise last_error
