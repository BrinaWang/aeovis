from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from aeo_eval.engine.rate_limiter import RateLimiter, RateLimiterConfig
from aeo_eval.engine.retry import RetryPolicy
from aeo_eval.models.analysis import StructuredCallResult
from aeo_eval.models.result import RunResult

logger = logging.getLogger(__name__)


class BaseEngine(ABC):
    """Abstract base class for AI answer engines."""

    name: str = "base"
    model_name: str = "base-model"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the engine.

        Args:
            config: Engine-specific configuration (API key, model, limits, etc.)
        """
        self.config = config or {}
        self._rate_limiter: Optional[RateLimiter] = None
        self._retry_policy: Optional[RetryPolicy] = None

    @abstractmethod
    def run(self, prompt_text: str) -> RunResult:
        """
        Run a prompt through the engine and return the result.

        Args:
            prompt_text: The prompt/question to send to the engine

        Returns:
            RunResult with the model's response and metadata
        """
        raise NotImplementedError

    def run_with_structured_output(
        self,
        prompt_text: str,
        schema: Dict[str, Any],
    ) -> "StructuredCallResult":
        """
        Run a prompt with structured output validation.

        This is useful for extracting specific fields (Module 3: Response Analysis).
        Subclasses should override to provide engine-specific implementation.

        Args:
            prompt_text: The prompt/question
            schema: JSON schema for validating structured output

        Returns:
            Parsed output plus token usage and cost.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support structured output"
        )

    # Cost-related methods

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Estimate cost for a given number of tokens.

        Args:
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens

        Returns:
            Estimated cost in dollars
        """
        costs = self.get_token_costs()
        input_cost = (prompt_tokens / 1000.0) * costs["input"]
        output_cost = (completion_tokens / 1000.0) * costs["output"]
        return input_cost + output_cost

    def get_token_costs(self) -> Dict[str, float]:
        """
        Get cost per 1k tokens for this engine.

        Returns:
            Dict with 'input' and 'output' keys (cost per 1k tokens)
        """
        return {
            "input": self.config.get("cost_per_1k_input_tokens", 0.001),
            "output": self.config.get("cost_per_1k_output_tokens", 0.001),
        }

    # Retry policy

    def get_retry_policy(self) -> RetryPolicy:
        """
        Get the retry policy for this engine.

        Returns:
            RetryPolicy instance
        """
        if self._retry_policy is None:
            max_retries = self.config.get("max_retries", 3)
            self._retry_policy = RetryPolicy(max_retries=max_retries)
        return self._retry_policy

    # Rate limiting

    def get_rate_limiter_config(self) -> RateLimiterConfig:
        """
        Get rate limiter configuration for this engine.

        Returns:
            RateLimiterConfig with TPM and RPM limits
        """
        return RateLimiterConfig(
            tokens_per_minute=self.config.get("rate_limit_tpm", 150000),
            requests_per_minute=self.config.get("rate_limit_rpm", 100),
        )

    def get_rate_limiter(self) -> RateLimiter:
        """
        Get or create the rate limiter for this engine.

        Returns:
            RateLimiter instance
        """
        if self._rate_limiter is None:
            config = self.get_rate_limiter_config()
            self._rate_limiter = RateLimiter(
                tpm_limit=config.tokens_per_minute,
                rpm_limit=config.requests_per_minute,
                config=config,
            )
        return self._rate_limiter

    # Context manager support for resource cleanup

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit (cleanup)."""
        await self.cleanup()

    async def cleanup(self):
        """
        Clean up engine resources (close connections, etc).

        Subclasses can override to implement cleanup logic.
        """
        pass
