from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Literal, Optional

from aeo_eval.analysis.extractor import extract_response
from aeo_eval.config import config as app_config
from aeo_eval.engine.base import BaseEngine
from aeo_eval.engine.factory import create_engine
from aeo_eval.models.analysis import ResponseAnalysisOutput
from aeo_eval.models.prompt import Prompt
from aeo_eval.models.result import RunResult, EvaluationRun
from aeo_eval.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

# Default competitor set used for brand/claim extraction (Module 3).
DEFAULT_COMPETITORS = ["Fivetran", "Confluent", "Kafka", "Oracle GoldenGate", "AWS DMS"]


class CostLimitExceeded(Exception):
    """Raised when cost limit is exceeded."""

    pass


@dataclass
class RunOptions:
    """Options for batch runs."""

    topic: Optional[str] = None
    persona: Optional[str] = None
    priority: Optional[str] = None
    dry_run: bool = False
    run_type: Literal["manual", "scheduled", "dashboard"] = "manual"
    notes: str = ""


class CostTracker:
    """Tracks and enforces cost limits for evaluation runs."""

    def __init__(self, limit_dollars: float):
        """Initialize cost tracker with a budget limit."""
        self.limit = limit_dollars
        self.spent = 0.0
        self.prompt_costs: List[tuple[str, float]] = []

    def add(self, prompt_id: str, cost: float) -> None:
        """
        Add cost for a prompt.

        Args:
            prompt_id: ID of the prompt
            cost: Cost in dollars

        Raises:
            CostLimitExceeded if total cost exceeds limit
        """
        self.spent += cost
        self.prompt_costs.append((prompt_id, cost))

        if self.spent > self.limit:
            raise CostLimitExceeded(
                f"Cost limit exceeded: ${self.spent:.2f} > ${self.limit:.2f}"
            )

    def remaining(self) -> float:
        """Get remaining budget in dollars."""
        return max(0.0, self.limit - self.spent)

    def summary(self) -> str:
        """Get human-readable cost summary."""
        return f"Spent ${self.spent:.2f} / ${self.limit:.2f} limit"

    def breakdown(self) -> Dict[str, float]:
        """Get cost breakdown by prompt."""
        breakdown = {}
        for prompt_id, cost in self.prompt_costs:
            breakdown[prompt_id] = breakdown.get(prompt_id, 0) + cost
        return breakdown


class Evaluator:
    """Orchestrates running prompts through an answer engine."""

    def __init__(self, engine: BaseEngine, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the evaluator.

        Args:
            engine: The answer engine to use
            config: Configuration dict with cost limits, etc.
        """
        self.engine = engine
        self.config = config or {}
        self.run_batch_id = str(uuid.uuid4())
        self.run_timestamp = datetime.now()
        self.cost_tracker = CostTracker(self.config.get("cost_limit_per_run", 35.0))
        self.run_type: Literal["manual", "scheduled", "dashboard"] = "manual"
        self.db_path = str(self.config.get("db_path") or app_config.general.output_db_path)
        self.store = SQLiteStore(self.db_path)
        self.store.init_db()

        # Module 3 analysis runs on a dedicated analyzer engine (Claude
        # by default, configurable via "analysis_provider"), falling
        # back to the engine under test when it can't be constructed
        # (e.g. no API key).
        analyzer_name = self.config.get("analysis_provider", "claude")
        if engine.name == analyzer_name:
            self.analyzer_engine: BaseEngine = engine
        else:
            try:
                self.analyzer_engine = create_engine(analyzer_name)
            except Exception as exc:
                logger.warning(
                    f"Analyzer engine '{analyzer_name}' unavailable "
                    f"({type(exc).__name__}: {exc}); falling back to "
                    f"'{engine.name}' for analysis."
                )
                self.analyzer_engine = engine

    def run_one(self, prompt: Prompt, options: Optional[RunOptions] = None) -> RunResult:
        """
        Run a single prompt through the engine.

        Args:
            prompt: The prompt to run
            options: Run options (dry_run, run_type, etc.)

        Returns:
            RunResult with engine output and metadata

        Raises:
            CostLimitExceeded if cost limit is exceeded
        """
        options = options or RunOptions()

        try:
            # Estimate cost before running (only if not dry_run)
            estimated_tokens = 1000 + 1500  # Rough estimate
            estimated_cost = self.engine.estimate_cost(
                prompt_tokens=1000,
                completion_tokens=1500,
            )

            # Check cost limit
            remaining = self.cost_tracker.remaining()
            if estimated_cost > remaining and not options.dry_run:
                raise CostLimitExceeded(
                    f"Insufficient budget: ${estimated_cost:.2f} > ${remaining:.2f} remaining"
                )

            # Run the engine (unless dry_run)
            if options.dry_run:
                # Return a dry-run result without calling the API
                result = RunResult(
                    run_id=f"{prompt.id}-{self.engine.name}-dryrun-{uuid.uuid4().hex[:12]}",
                    run_batch_id=self.run_batch_id,
                    prompt_id=prompt.id,
                    engine=self.engine.name,
                    model=self.engine.model_name,
                    status="dry_run",
                    response_text=None,
                    error=None,
                    latency_ms=0,
                    estimated_cost=estimated_cost,
                    engine_name=self.engine.__class__.__name__,
                    run_timestamp=self.run_timestamp,
                    run_type=options.run_type,
                )
            else:
                # Run the engine
                result = self.engine.run(prompt.prompt)
                result.prompt_id = prompt.id
                result.run_batch_id = self.run_batch_id
                result.run_type = options.run_type
                result.engine_name = self.engine.__class__.__name__
                result.run_timestamp = self.run_timestamp

                # Persist EVERY outcome (success, failed, timeout,
                # rate_limited) before anything that can raise.
                self._save_result_best_effort(result)

                # Track actual cost (may raise CostLimitExceeded)
                if result.actual_cost is not None:
                    self.cost_tracker.add(prompt.id, result.actual_cost)

                # Extract analysis — best-effort, success only.
                if result.status == "success" and result.response_text:
                    self._extract_and_store_analysis(prompt, result)

            return result

        except CostLimitExceeded as e:
            logger.warning(f"Cost limit exceeded: {e}")
            raise

        except Exception as exc:
            logger.error(f"Error running prompt {prompt.id}: {type(exc).__name__}: {exc}")
            failed = RunResult(
                run_id=f"{prompt.id}-{self.engine.name}-error-{uuid.uuid4().hex[:12]}",
                run_batch_id=self.run_batch_id,
                prompt_id=prompt.id,
                engine=self.engine.name,
                model=self.engine.model_name,
                status="failed",
                response_text=None,
                error=str(exc),
                latency_ms=None,
                engine_name=self.engine.__class__.__name__,
                run_timestamp=self.run_timestamp,
                run_type=options.run_type,
            )
            self._save_result_best_effort(failed)
            return failed

    def _save_result_best_effort(self, result: RunResult) -> None:
        """Persist a result; storage failures must not fail the run."""
        try:
            self.store.save_run(result)
        except Exception as exc:
            logger.warning(
                f"Failed to persist result {result.run_id}: {type(exc).__name__}: {exc}"
            )

    def _extract_and_store_analysis(self, prompt: Prompt, result: RunResult) -> None:
        """
        Run Module 3 extraction (brands, positions, claims, sentiment) on a
        completed response, then persist its analysis.

        The extracted analysis dict is also attached to ``result.analysis``
        for callers that want it without re-querying storage.

        The raw response has already been persisted by _save_result_best_effort.

        Extraction/storage failures are logged and swallowed rather than
        propagated: the prompt run itself already succeeded, and a
        downstream analysis/persistence issue shouldn't be reported as a
        failed evaluation run.
        """
        try:
            analysis = extract_response(
                response_text=result.response_text,
                engine=self.analyzer_engine,
                competitors=DEFAULT_COMPETITORS,
            )
            result.analysis = analysis

            analysis_cost = analysis.get("analysis_cost", 0.0)
            if analysis_cost:
                try:
                    self.cost_tracker.add(f"{prompt.id}:analysis", analysis_cost)
                except CostLimitExceeded:
                    logger.warning(
                        "Cost limit reached (including analysis spend); "
                        "remaining prompts will not run."
                    )

            # "Recommended" isn't a direct field on the extractor output;
            # treat a mention with an overall positive sentiment as a
            # recommendation.
            striim_mentioned = bool(analysis.get("striim_mentioned", False))
            striim_recommended = striim_mentioned and analysis.get("sentiment") == "positive"

            analysis_output = ResponseAnalysisOutput(
                raw_response_id=result.run_id,
                striim_mentioned=striim_mentioned,
                striim_recommended=striim_recommended,
                striim_position=analysis.get("striim_position"),
                brands_found=json.dumps(analysis.get("brands_found", [])),
                claims=json.dumps(analysis.get("striim_claims", [])),
                citations=json.dumps(analysis.get("citations", [])),
                extraction_confidence=analysis.get("confidence", 0.0),
                flagged_for_review=bool(analysis.get("flagged_for_review", False)),
            )
            self.store.save_analysis(analysis_output)

        except Exception as exc:
            logger.warning(
                f"Analysis extraction/storage failed for prompt {prompt.id}: "
                f"{type(exc).__name__}: {exc}"
            )

    def run_batch(
        self,
        prompts: Iterable[Prompt],
        options: Optional[RunOptions] = None,
    ) -> tuple[List[RunResult], EvaluationRun]:
        """
        Run multiple prompts through the engine.

        Args:
            prompts: Iterable of prompts to run
            options: Run options (filtering, dry_run, etc.)

        Returns:
            Tuple of (list of RunResults, EvaluationRun summary)
        """
        options = options or RunOptions()
        self.run_type = options.run_type

        # Filter prompts by topic/persona/priority if specified
        filtered_prompts = self._filter_prompts(prompts, options)
        prompts_list = list(filtered_prompts)

        logger.info(
            f"Running {len(prompts_list)} prompt(s) with engine={self.engine.name}, "
            f"dry_run={options.dry_run}"
        )

        # Calculate cost estimate before running
        total_estimated_cost = 0.0
        for prompt in prompts_list:
            total_estimated_cost += self.engine.estimate_cost(1000, 1500)

        logger.info(f"Estimated cost: ${total_estimated_cost:.2f}")

        if options.dry_run:
            logger.info("DRY RUN: Would cost ${total_estimated_cost:.2f} (no API calls made)")

        # Run all prompts
        results: List[RunResult] = []
        succeeded = 0
        failed = 0
        total_input_tokens = 0
        total_output_tokens = 0

        for prompt in prompts_list:
            try:
                result = self.run_one(prompt, options)
                results.append(result)

                if result.status == "success":
                    succeeded += 1
                    if result.input_tokens:
                        total_input_tokens += result.input_tokens
                    if result.output_tokens:
                        total_output_tokens += result.output_tokens
                else:
                    failed += 1

            except CostLimitExceeded as e:
                logger.warning(f"Cost limit reached: {e}")
                # Add a synthetic result for batch bookkeeping only. If the
                # limit tripped on this prompt's own cost (rather than the
                # analysis spend that follows a successful run), run_one has
                # already persisted the real result for it — do not also
                # persist this one, or the prompt is double-counted in
                # raw_responses.
                cost_limit_result = RunResult(
                    run_id=f"cost-limit-{uuid.uuid4().hex[:12]}",
                    run_batch_id=self.run_batch_id,
                    prompt_id=prompt.id,
                    engine=self.engine.name,
                    model=self.engine.model_name,
                    status="cost_limit_exceeded",
                    response_text=None,
                    error=str(e),
                    latency_ms=None,
                    engine_name=self.engine.__class__.__name__,
                    run_timestamp=self.run_timestamp,
                    run_type=options.run_type,
                )
                results.append(cost_limit_result)
                failed += 1
                # Stop running further prompts
                break

        # Create summary
        evaluation_run = EvaluationRun(
            run_id=self.run_batch_id,
            run_timestamp=self.run_timestamp,
            engine=self.engine.name,
            model_version=self.engine.model_name,
            prompts_run=len(results),
            prompts_succeeded=succeeded,
            prompts_failed=failed,
            # cost_tracker is batch-scoped and records both engine spend
            # and analyzer LLM spend (including the add() call that raises
            # CostLimitExceeded), unlike summing successful results' own
            # actual_cost which misses analysis spend entirely.
            total_cost=self.cost_tracker.spent,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            run_type=options.run_type,
            filters_applied={
                "topic": options.topic,
                "persona": options.persona,
                "priority": options.priority,
            },
            run_notes=options.notes,
            duration_seconds=(datetime.now() - self.run_timestamp).total_seconds(),
        )

        if not options.dry_run:
            try:
                self.store.save_evaluation_run(evaluation_run)
            except Exception as exc:
                logger.warning(
                    f"Failed to persist evaluation run summary: {type(exc).__name__}: {exc}"
                )

        logger.info(
            f"Batch complete: {succeeded} succeeded, {failed} failed, "
            f"cost=${evaluation_run.total_cost:.2f}, {evaluation_run.success_rate:.1f}% success rate"
        )

        return results, evaluation_run

    def _filter_prompts(
        self,
        prompts: Iterable[Prompt],
        options: RunOptions,
    ) -> Iterable[Prompt]:
        """Filter prompts based on run options."""
        for prompt in prompts:
            if options.topic and prompt.topic != options.topic:
                continue
            if options.persona and prompt.persona != options.persona:
                continue
            if options.priority and prompt.priority != options.priority:
                continue
            if not prompt.enabled:
                continue

            yield prompt
