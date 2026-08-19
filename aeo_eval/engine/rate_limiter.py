"""Rate limiting for API calls to prevent hitting provider limits."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiting."""
    tokens_per_minute: int = 150000  # TPM (tokens per minute)
    requests_per_minute: int = 100  # RPM (requests per minute)


@dataclass
class RateLimiter:
    """Token bucket rate limiter for API calls."""

    tpm_limit: int
    rpm_limit: int
    config: RateLimiterConfig = field(default_factory=RateLimiterConfig)

    # Token bucket state (TPM)
    tpm_tokens: float = field(init=False)
    tpm_last_refill: float = field(init=False)

    # Request bucket state (RPM)
    rpm_tokens: float = field(init=False)
    rpm_last_refill: float = field(init=False)

    def __post_init__(self):
        """Initialize token buckets."""
        self.tpm_tokens = self.tpm_limit
        self.tpm_last_refill = time.time()
        self.rpm_tokens = self.rpm_limit
        self.rpm_last_refill = time.time()

    def _refill_bucket(self, bucket_type: str) -> None:
        """Refill token bucket based on elapsed time."""
        now = time.time()

        if bucket_type == "tpm":
            elapsed = now - self.tpm_last_refill
            # Refill rate: tpm_limit tokens per 60 seconds
            new_tokens = elapsed * (self.tpm_limit / 60.0)
            self.tpm_tokens = min(self.tpm_limit, self.tpm_tokens + new_tokens)
            self.tpm_last_refill = now
        elif bucket_type == "rpm":
            elapsed = now - self.rpm_last_refill
            # Refill rate: rpm_limit requests per 60 seconds
            new_tokens = elapsed * (self.rpm_limit / 60.0)
            self.rpm_tokens = min(self.rpm_limit, self.rpm_tokens + new_tokens)
            self.rpm_last_refill = now

    def wait_for_tokens(
        self,
        prompt_tokens: int,
        completion_tokens: int = 1000,
    ) -> float:
        """
        Wait until enough tokens and requests are available.

        Args:
            prompt_tokens: Estimated input tokens
            completion_tokens: Estimated output tokens (default 1000)

        Returns:
            Time waited in seconds
        """
        total_tokens = prompt_tokens + completion_tokens
        start_time = time.time()

        while True:
            # Refill buckets
            self._refill_bucket("tpm")
            self._refill_bucket("rpm")

            # Check both limits
            tpm_ok = self.tpm_tokens >= total_tokens
            rpm_ok = self.rpm_tokens >= 1

            if tpm_ok and rpm_ok:
                # Consume tokens
                self.tpm_tokens -= total_tokens
                self.rpm_tokens -= 1
                break

            # Calculate wait time
            tpm_wait = 0.0
            if not tpm_ok:
                needed = total_tokens - self.tpm_tokens
                tpm_wait = (needed / self.tpm_limit) * 60.0

            rpm_wait = 0.0
            if not rpm_ok:
                needed = 1 - self.rpm_tokens
                rpm_wait = (needed / self.rpm_limit) * 60.0

            wait_time = max(tpm_wait, rpm_wait, 0.1)  # Minimum 100ms

            logger.debug(
                f"Rate limited: waiting {wait_time:.2f}s "
                f"(TPM: {self.tpm_tokens:.0f}/{self.tpm_limit}, "
                f"RPM: {self.rpm_tokens:.1f}/{self.rpm_limit})"
            )

            time.sleep(min(wait_time, 1.0))  # Sleep max 1s at a time

        elapsed = time.time() - start_time
        if elapsed > 0.1:
            logger.info(f"Rate limit wait: {elapsed:.2f}s")

        return elapsed

    def acquire_tokens(
        self,
        prompt_tokens: int,
        completion_tokens: int = 1000,
    ) -> float:
        """
        Acquire tokens for a request, blocking if necessary.

        This is a wrapper around wait_for_tokens for clarity.

        Args:
            prompt_tokens: Estimated input tokens
            completion_tokens: Estimated output tokens

        Returns:
            Time waited in seconds
        """
        return self.wait_for_tokens(prompt_tokens, completion_tokens)

    def reset(self) -> None:
        """Reset rate limiter to full capacity."""
        self.tpm_tokens = self.tpm_limit
        self.rpm_tokens = self.rpm_limit
        self.tpm_last_refill = time.time()
        self.rpm_last_refill = time.time()

    def status(self) -> dict:
        """Get current rate limiter status."""
        self._refill_bucket("tpm")
        self._refill_bucket("rpm")

        return {
            "tpm_available": int(self.tpm_tokens),
            "tpm_limit": self.tpm_limit,
            "tpm_percent": (self.tpm_tokens / self.tpm_limit) * 100,
            "rpm_available": self.rpm_tokens,
            "rpm_limit": self.rpm_limit,
            "rpm_percent": (self.rpm_tokens / self.rpm_limit) * 100,
        }
