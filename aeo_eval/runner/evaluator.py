"""Module 2 + Module 3 runner: execute prompts and persist answers/analysis.

``Evaluator`` owns one evaluation *batch* (``run_batch_id``, which becomes
``evaluation_runs.run_id``). For each prompt it:

1. reserves an estimated budget slice (``CostTracker.try_reserve_budget``),
2. calls the answer engine on a worker thread (up to 4 in flight),
3. persists the ``RunResult`` to ``raw_responses`` **whatever its status**,
4. on success, runs Module 3 extraction through the *analyzer* engine
   and persists a ``response_analysis`` row, folding the analyzer's cost
   into the same ``CostTracker``,
5. after all futures complete, upserts the batch summary into
   ``evaluation_runs``.

Two engines are involved: the engine under test (``self.engine``) and the
analyzer (``self.analyzer_engine``). The analyzer defaults to Claude for
real engines and to the engine itself for mocks; see ``__init__``.

Cost enforcement is per batch and thread-safe. Because reservations use a
fixed estimate (``_EST_INPUT_TOKENS``/``_EST_OUTPUT_TOKENS``) and are
replaced by actual cost only when a result reports ``actual_cost``, a
failed call keeps its (conservative) reservation. The daily limit is not
checked here; the orchestrator checks it before constructing an Evaluator.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Engines that produce synthetic responses. Runs on these stay fully
# offline: they act as their own Module 3 analyzer rather than calling
# out to a real provider.
MOCK_ENGINE_NAMES = frozenset({"mock", "random-mock"})

# Fallback competitor set for brand/claim extraction (Module 3), used only
# when config.evaluation.competitors is empty. See competitors_to_track().
DEFAULT_COMPETITORS = ["Fivetran", "Confluent", "Kafka", "Oracle GoldenGate", "AWS DMS"]


def competitors_to_track() -> List[str]:
    """Competitor names Module 3 should detect.

    Read from ``config.evaluation.competitors`` at call time so edits to
    the config object (dashboard, tests) take effect without a restart;
    falls back to DEFAULT_COMPETITORS when the configured list is empty.
    """
    configured = list(getattr(app_config.evaluation, "competitors", None) or [])
    return configured or list(DEFAULT_COMPETITORS)

# Assumed per-prompt token counts behind every pre-run cost estimate and
# budget reservation.
_EST_INPUT_TOKENS = 1000
_EST_OUTPUT_TOKENS = 1500


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
    """Tracks and enforces cost limits for evaluation runs.

    Thread-safe cost tracking for concurrent prompt execution. Cost limit is
    enforced when add() is called. With concurrent execution, multiple prompts
    in flight may finish at the same time; the limit may be exceeded by at most
    the cost of concurrent requests that complete after the limit check.
    """

    def __init__(self, limit_dollars: float):
        """Initialize cost tracker with a budget limit."""
        self.limit = limit_dollars
        self.spent = 0.0
        self.prompt_costs: List[tuple[str, float]] = []
        self._lock = threading.Lock()
        self.limit_exceeded = False

    def add(self, prompt_id: str, cost: float) -> None:
        """
        Add cost for a prompt.

        Args:
            prompt_id: ID of the prompt
            cost: Cost in dollars

        Raises:
            CostLimitExceeded if total cost exceeds limit
        """
        with self._lock:
            self.spent += cost
            self.prompt_costs.append((prompt_id, cost))

            if self.spent > self.limit:
                self.limit_exceeded = True
                raise CostLimitExceeded(
                    f"Cost limit exceeded: ${self.spent:.2f} > ${self.limit:.2f}"
                )

    def remaining(self) -> float:
        """Get remaining budget in dollars."""
        with self._lock:
            return max(0.0, self.limit - self.spent)

    def can_afford(self, estimated_cost: float) -> bool:
        """
        Check if estimated cost fits within remaining budget.

        Args:
            estimated_cost: Estimated cost to check

        Returns:
            True if cost would not exceed limit, False otherwise
        """
        with self._lock:
            return self.spent + estimated_cost <= self.limit

    def try_reserve_budget(self, prompt_id: str, estimated_cost: float) -> tuple[bool, str]:
        """
        Atomically check if budget is available and pre-reserve it for a prompt.

        This ensures that concurrent execution never exceeds the limit by reserving
        estimated budget before execution. Actual cost replaces reserved cost later.

        Args:
            prompt_id: ID of the prompt
            estimated_cost: Estimated cost to reserve

        Returns:
            (success: bool, reservation_id: str) — if success is True, budget was
            reserved and the reservation_id can be used to confirm actual cost later
        """
        with self._lock:
            if self.spent + estimated_cost > self.limit:
                return False, ""

            reservation_id = f"reserved-{prompt_id}"
            self.spent += estimated_cost
            self.prompt_costs.append((reservation_id, estimated_cost))
            return True, reservation_id

    def confirm_actual_cost(self, reservation_id: str, prompt_id: str, actual_cost: float) -> None:
        """
        Replace a budget reservation with actual cost.

        Args:
            reservation_id: The ID from try_reserve_budget
            prompt_id: The prompt ID
            actual_cost: The actual cost from the API
        """
        with self._lock:
            for i, (cost_id, cost_amount) in enumerate(self.prompt_costs):
                if cost_id == reservation_id:
                    self.prompt_costs[i] = (prompt_id, actual_cost)
                    self.spent = self.spent - cost_amount + actual_cost
                    break

    def summary(self) -> str:
        """Get human-readable cost summary."""
        with self._lock:
            return f"Spent ${self.spent:.2f} / ${self.limit:.2f} limit"

    def breakdown(self) -> Dict[str, float]:
        """Get cost breakdown by prompt."""
        with self._lock:
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
        #
        # Mock engines analyze themselves instead: their responses are
        # synthetic, so paying for a real analyzer call per prompt buys
        # nothing and makes an otherwise instant, free run cost real
        # money and minutes of wall-clock. Set "analysis_provider"
        # explicitly to override.
        default_analyzer = engine.name if engine.name in MOCK_ENGINE_NAMES else "claude"
        analyzer_name = self.config.get("analysis_provider", default_analyzer)
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

    def run_one(
        self,
        prompt: Prompt,
        options: Optional[RunOptions] = None,
        *,
        budget_reserved: bool = False,
    ) -> RunResult:
        """
        Run a single prompt through the engine.

        Args:
            prompt: The prompt to run
            options: Run options (dry_run, run_type, etc.)
            budget_reserved: Set by run_batch, which already reserved this
                prompt's estimated cost via try_reserve_budget. Leave False
                for a direct call so the per-run limit is enforced here
                instead — reserving twice would double-count the prompt.

        Returns:
            RunResult with engine output and metadata

        Raises:
            CostLimitExceeded if cost limit is exceeded
        """
        options = options or RunOptions()

        try:
            # Note: Cost limit checking is done in run_batch before submitting
            # prompts to the executor (via try_reserve_budget). Here we only
            # track analysis costs. For dry_run, no API calls or cost tracking.

            # Run the engine (unless dry_run)
            if options.dry_run:
                # Return a dry-run result without calling the API
                estimated_cost = self.engine.estimate_cost(_EST_INPUT_TOKENS, _EST_OUTPUT_TOKENS)
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
                # run_batch reserves each prompt's budget before submitting
                # it here. A direct run_one() call has no reservation, so
                # the per-run limit has to be enforced at this entry point
                # or it isn't enforced at all.
                if not budget_reserved:
                    estimated_cost = self.engine.estimate_cost(_EST_INPUT_TOKENS, _EST_OUTPUT_TOKENS)
                    if not self.cost_tracker.can_afford(estimated_cost):
                        raise CostLimitExceeded(
                            f"Cost limit exceeded: estimated ${estimated_cost:.2f} "
                            f"> ${self.cost_tracker.remaining():.2f} remaining "
                            f"of ${self.cost_tracker.limit:.2f}"
                        )

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

                # Note: Actual cost tracking is done in run_batch after prompt completion
                # (via confirm_actual_cost from reservation). This ensures atomic
                # cost tracking with the budget reservation system.

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
                competitors=competitors_to_track(),
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
            total_estimated_cost += self.engine.estimate_cost(_EST_INPUT_TOKENS, _EST_OUTPUT_TOKENS)

        logger.info(f"Estimated cost: ${total_estimated_cost:.2f}")

        if options.dry_run:
            logger.info("DRY RUN: Would cost ${total_estimated_cost:.2f} (no API calls made)")

        # Run all prompts concurrently with max 4 workers.
        # Cost limits are enforced per-run via CostTracker (thread-safe).
        # Per-day limits are checked before pipeline starts in orchestrator.py.
        # Token counting (input/output) happens as results complete in main thread.
        # Budget is checked before submitting each prompt to prevent overspend.
        results: List[RunResult] = []
        succeeded = 0
        failed = 0
        total_input_tokens = 0
        total_output_tokens = 0

        max_workers = min(4, len(prompts_list))
        prompt_reservations = {}  # Maps future -> (prompt, reservation_id)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for prompt in prompts_list:
                # Atomically check and reserve budget before submitting to executor
                estimated_cost = self.engine.estimate_cost(_EST_INPUT_TOKENS, _EST_OUTPUT_TOKENS)

                if not options.dry_run:
                    reserved, reservation_id = self.cost_tracker.try_reserve_budget(
                        prompt.id, estimated_cost
                    )
                    if not reserved:
                        logger.warning(
                            f"Insufficient budget for prompt {prompt.id}: "
                            f"${estimated_cost:.2f} estimated > "
                            f"${self.cost_tracker.remaining():.2f} remaining"
                        )
                        cost_limit_result = RunResult(
                            run_id=f"cost-limit-{uuid.uuid4().hex[:12]}",
                            run_batch_id=self.run_batch_id,
                            prompt_id=prompt.id,
                            engine=self.engine.name,
                            model=self.engine.model_name,
                            status="cost_limit_exceeded",
                            response_text=None,
                            error=f"Insufficient budget: ${estimated_cost:.2f} > ${self.cost_tracker.remaining():.2f} remaining",
                            latency_ms=None,
                            engine_name=self.engine.__class__.__name__,
                            run_timestamp=self.run_timestamp,
                            run_type=options.run_type,
                        )
                        results.append(cost_limit_result)
                        failed += 1
                        continue
                else:
                    reservation_id = None

                future = executor.submit(
                    self.run_one, prompt, options, budget_reserved=True
                )
                futures[future] = prompt
                prompt_reservations[future] = reservation_id

            for future in as_completed(futures):
                prompt = futures[future]
                reservation_id = prompt_reservations.get(future)

                try:
                    result = future.result()
                    results.append(result)

                    # Confirm actual cost if we had a reservation
                    if reservation_id and result.actual_cost is not None:
                        self.cost_tracker.confirm_actual_cost(
                            reservation_id, prompt.id, result.actual_cost
                        )

                    if result.status == "success":
                        succeeded += 1
                        if result.input_tokens is not None:
                            total_input_tokens += result.input_tokens
                        if result.output_tokens is not None:
                            total_output_tokens += result.output_tokens
                    else:
                        failed += 1

                except CostLimitExceeded as e:
                    logger.warning(f"Cost limit reached: {e}")
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

                except Exception as e:
                    logger.error(f"Error in concurrent execution: {type(e).__name__}: {e}")
                    failed_result = RunResult(
                        run_id=f"error-{uuid.uuid4().hex[:12]}",
                        run_batch_id=self.run_batch_id,
                        prompt_id=prompt.id,
                        engine=self.engine.name,
                        model=self.engine.model_name,
                        status="failed",
                        response_text=None,
                        error=str(e),
                        latency_ms=None,
                        engine_name=self.engine.__class__.__name__,
                        run_timestamp=self.run_timestamp,
                        run_type=options.run_type,
                    )
                    results.append(failed_result)
                    failed += 1

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
        # Priority is compared case-insensitively: question.json stores
        # "high"/"medium"/"low" while the CLI offers "High"/"Medium"/"Low".
        wanted_priority = (options.priority or "").strip().lower()
        for prompt in prompts:
            if options.topic and prompt.topic != options.topic:
                continue
            if options.persona and prompt.persona != options.persona:
                continue
            if wanted_priority and (prompt.priority or "").strip().lower() != wanted_priority:
                continue
            if not prompt.enabled:
                continue

            yield prompt
