"""Claude API engine implementation for the AEO Visibility Platform."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from anthropic import Anthropic, APIError, APITimeoutError, RateLimitError

from aeo_eval.engine.base import BaseEngine
from aeo_eval.engine.retry import RetryManager
from aeo_eval.models.analysis import StructuredCallResult
from aeo_eval.models.result import RunResult

logger = logging.getLogger(__name__)


class ClaudeEngine(BaseEngine):
    """AI engine that uses Anthropic's Claude API."""

    name = "claude"
    model_name = "claude-opus-5"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Claude engine with API key and configuration.

        Args:
            config: Configuration dict with:
                - api_key: Anthropic API key (or from ANTHROPIC_API_KEY env var)
                - model_name: Claude model to use (default: claude-opus-5)
                - rate_limit_tpm: Tokens per minute (default: 150000)
                - rate_limit_rpm: Requests per minute (default: 100)
                - timeout_seconds: API timeout (default: 60)
                - cost_per_1k_input_tokens: Input token cost
                - cost_per_1k_output_tokens: Output token cost
        """
        super().__init__(config)

        api_key = self.config.get("api_key")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY required. Set via config or ANTHROPIC_API_KEY env var."
            )

        self.client = Anthropic(api_key=api_key)
        self.model_name = self.config.get("model_name", "claude-opus-5")
        self.timeout = self.config.get("timeout_seconds", 60)

        # Initialize retry manager
        self._retry_manager = RetryManager(self.get_retry_policy())

        # Initialize rate limiter
        self._rate_limiter_instance = self.get_rate_limiter()

        logger.info(
            f"Initialized ClaudeEngine with model={self.model_name}, "
            f"rate_limits=(TPM: {self._rate_limiter_instance.tpm_limit}, "
            f"RPM: {self._rate_limiter_instance.rpm_limit})"
        )

    def run(self, prompt_text: str) -> RunResult:
        """
        Run a prompt through Claude and return the result.

        Args:
            prompt_text: The prompt/question to send

        Returns:
            RunResult with the response and metadata
        """
        run_id = str(uuid4())
        run_batch_id = ""  # Will be set by Evaluator
        start_time = datetime.now()

        try:
            # Wait for rate limit tokens
            wait_time = self._rate_limiter_instance.wait_for_tokens(
                prompt_tokens=100,  # Rough estimate for prompt
                completion_tokens=1000,  # Rough estimate for response
            )

            # Make API call with retry logic
            def _call_claude():
                return self.client.messages.create(
                    model=self.model_name,
                    max_tokens=2000,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt_text,
                        }
                    ],
                    timeout=self.timeout,
                )

            logger.debug(f"Calling Claude API (model={self.model_name})")
            message = self._retry_manager.retry(_call_claude)

            # Extract response and token counts
            response_text = message.content[0].text if message.content else ""
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens

            # Calculate actual cost
            actual_cost = self.estimate_cost(input_tokens, output_tokens)

            # Calculate latency
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            logger.info(
                f"Claude API success: {input_tokens} input + {output_tokens} output tokens, "
                f"cost=${actual_cost:.4f}, latency={latency_ms}ms"
            )

            return RunResult(
                run_id=run_id,
                run_batch_id=run_batch_id,
                prompt_id="",  # Will be set by Evaluator
                engine="claude",
                model=self.model_name,
                status="success",
                response_text=response_text,
                error=None,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_cost=actual_cost,
                engine_name="ClaudeEngine",
                run_timestamp=start_time,
                run_type="manual",
            )

        except RateLimitError as e:
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Rate limit error: {e}")
            return RunResult(
                run_id=run_id,
                run_batch_id=run_batch_id,
                prompt_id="",
                engine="claude",
                model=self.model_name,
                status="rate_limited",
                response_text=None,
                error=str(e),
                latency_ms=latency_ms,
                engine_name="ClaudeEngine",
                run_timestamp=start_time,
                run_type="manual",
            )

        except APITimeoutError as e:
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Timeout error: {e}")
            return RunResult(
                run_id=run_id,
                run_batch_id=run_batch_id,
                prompt_id="",
                engine="claude",
                model=self.model_name,
                status="timeout",
                response_text=None,
                error=str(e),
                latency_ms=latency_ms,
                engine_name="ClaudeEngine",
                run_timestamp=start_time,
                run_type="manual",
            )

        except APIError as e:
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"API error: {e}")
            return RunResult(
                run_id=run_id,
                run_batch_id=run_batch_id,
                prompt_id="",
                engine="claude",
                model=self.model_name,
                status="failed",
                response_text=None,
                error=str(e),
                latency_ms=latency_ms,
                engine_name="ClaudeEngine",
                run_timestamp=start_time,
                run_type="manual",
            )

        except Exception as e:
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            return RunResult(
                run_id=run_id,
                run_batch_id=run_batch_id,
                prompt_id="",
                engine="claude",
                model=self.model_name,
                status="failed",
                response_text=None,
                error=f"{type(e).__name__}: {e}",
                latency_ms=latency_ms,
                engine_name="ClaudeEngine",
                run_timestamp=start_time,
                run_type="manual",
            )

    def run_with_structured_output(
        self,
        prompt_text: str,
        schema: Dict[str, Any],
    ) -> StructuredCallResult:
        """Run a prompt with schema-enforced structured output.

        Uses the Messages API's output_config.format (json_schema), so
        the response text is guaranteed to be valid JSON matching the
        schema. Used by Module 3 (Response Analysis).
        """
        logger.debug("Running Claude with structured output schema")

        self._rate_limiter_instance.wait_for_tokens(
            prompt_tokens=100, completion_tokens=1000
        )

        def _call_claude_structured():
            return self.client.messages.create(
                model=self.model_name,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt_text}],
                output_config={
                    "format": {"type": "json_schema", "schema": schema}
                },
                timeout=self.timeout,
            )

        message = self._retry_manager.retry(_call_claude_structured)
        response_text = message.content[0].text if message.content else ""
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse structured response as JSON: {response_text}")
            data = {"raw_response": response_text}

        return StructuredCallResult(
            data=data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=self.estimate_cost(input_tokens, output_tokens),
        )

    def get_token_costs(self) -> Dict[str, float]:
        """
        Get current token costs for Claude Opus 5.

        These should be updated as pricing changes.

        Returns:
            Dict with 'input' and 'output' costs per 1k tokens
        """
        return {
            "input": self.config.get("cost_per_1k_input_tokens", 0.003),
            "output": self.config.get("cost_per_1k_output_tokens", 0.015),
        }
