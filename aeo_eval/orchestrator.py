"""Full pipeline orchestration.

Wires together the answer-engine runner (Module 2), response analysis
extraction (Module 3, integrated into the evaluator), visibility metrics
(Module 4), website accessibility checks (Module 6, optional),
citation deduplication (Module 5), gap detection (Module 8), and
recommendation generation with auto-approval (Module 9) into a single
top-level entry point. Module 6 is completely separate from visibility
metrics and only runs if enabled in config.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import List, Optional

from aeo_eval.citations.deduplicator import CitationDeduplicator
from aeo_eval.config import config as app_config
from aeo_eval.engine.base import BaseEngine
from aeo_eval.gaps.detector import GapDetector
from aeo_eval.metrics.calculator import MetricsCalculator
from aeo_eval.models.prompt import Prompt
from aeo_eval.recommendations.approval import should_auto_approve
from aeo_eval.recommendations.generator import RecommendationGenerator
from aeo_eval.runner.evaluator import Evaluator, RunOptions
from aeo_eval.storage.sqlite_store import SQLiteStore, resolve_sqlite_target
from aeo_eval.website_accessibility import WebsiteAccessibilityChecker

logger = logging.getLogger(__name__)


class AEOPipelineOrchestrator:
    """Orchestrate the full AEO evaluation pipeline.

    This is the top-level entry point for running prompts end-to-end:
    answer engine -> analysis -> metrics -> [website accessibility checks] ->
    citations -> gaps -> recommendations -> auto-approval. Module 6
    (website accessibility) is optional and controlled by config.
    Callers (e.g. the CLI) should use this instead of driving ``Evaluator``
    directly.
    """

    def __init__(self, engine: BaseEngine, config: Optional[dict] = None):
        """Initialize orchestrator.

        Args:
            engine: The answer engine to run prompts through.
            config: Configuration dict. Recognized keys include
                ``db_path`` (SQLite database path, or ``":memory:"``) and
                ``cost_limit_per_run`` (forwarded to the Evaluator).
        """
        self.engine = engine
        self.config = config or {}
        self.db_path = str(self.config.get("db_path") or app_config.general.output_db_path)
        self.store = SQLiteStore(self.db_path)

        # Resolve the same connection target the store uses, so the
        # long-lived connection this orchestrator holds for the duration
        # of a pipeline run observes the same database (including, for
        # ":memory:", the same shared-cache in-memory database used by
        # every short-lived connection SQLiteStore opens internally).
        self._conn_target, self._conn_uri = resolve_sqlite_target(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the pipeline's target database."""
        conn = sqlite3.connect(self._conn_target, uri=self._conn_uri)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def run_full_pipeline(
        self,
        prompts: List[Prompt],
        options: Optional[RunOptions] = None,
    ) -> dict:
        """
        Run full evaluation and analysis pipeline.

        Pipeline:
        1. Run prompts through answer engine
        2. Extract analysis (brands, claims, sentiment) - via evaluator
        3. Calculate visibility metrics (Module 4)
        4. Website accessibility checks (Module 6) - optional, if enabled in config
        5. Deduplicate and classify citations (Module 5)
        6. Detect gaps (Module 8)
        7. Generate recommendations (Module 9)
        8. Auto-approve high-confidence recommendations

        Module 6 is completely separate from visibility metrics and only runs
        if run_website_accessibility_checks is enabled in config.evaluation.

        Args:
            prompts: List of Prompt objects to evaluate
            options: Run options (topic filter, etc.)

        Returns:
            Summary dict with run_id, num_prompts, num_gaps,
            num_recommendations, num_auto_approved.
        """
        logger.info(f"Starting pipeline for {len(prompts)} prompts")

        # Hold one connection open for the entire pipeline. This is what
        # keeps a ":memory:" (shared-cache) database alive across the many
        # short-lived connections opened internally by the Evaluator/
        # SQLiteStore and by the module components below.
        conn = self._connect()
        try:
            self.store.init_db()
            purged = self.store.apply_retention()
            purged = {k: v for k, v in purged.items() if v}
            if purged:
                logger.info(f"Retention purge removed rows: {purged}")

            # Step 1: Run evaluation (Module 2). Analysis extraction
            # (Module 3 - brands, positions, claims, sentiment) is already
            # integrated into Evaluator.run_one/run_batch.
            evaluator = Evaluator(self.engine, self.config)
            results, evaluation_run = evaluator.run_batch(prompts, options)
            run_id = evaluator.run_batch_id

            logger.info(
                f"Evaluation complete. Run ID: {run_id} "
                f"({evaluation_run.prompts_succeeded} succeeded, "
                f"{evaluation_run.prompts_failed} failed)"
            )

            # Generate test data for mock engines (properly associated with evaluation run)
            if self.engine.name == "random-mock":
                self.engine.generate_test_data_for_run(run_id)

            # Persist prompt metadata (topic/persona/priority) so the
            # by-topic metrics breakdown below can join against it.
            self.store.save_prompts(prompts)

            # Step 2: Metrics (Module 4)
            calculator = MetricsCalculator(conn)
            overall_metrics = calculator.calculate_metrics_for_run(run_id)
            if overall_metrics:
                self.store.save_metrics(run_id, overall_metrics)
            topic_metrics = calculator.calculate_metrics_by_topic(run_id)
            for metrics in topic_metrics:
                self.store.save_metrics(run_id, metrics)
            logger.info(
                f"Metrics calculated and stored (overall + {len(topic_metrics)} topic breakdowns)"
            )

            # Step 2.5: Website Accessibility Checks (Module 6) - optional
            if app_config.evaluation.run_website_accessibility_checks:
                try:
                    checker = WebsiteAccessibilityChecker()
                    important_pages = app_config.evaluation.important_striim_pages
                    crawlers = app_config.evaluation.crawlers

                    logger.info(
                        f"Running Module 6: Website Accessibility checks on {len(important_pages)} pages for {len(crawlers)} crawlers"
                    )

                    checks = checker.check_pages(important_pages, crawlers)

                    for check in checks:
                        check['run_id'] = run_id

                    if checks:
                        self.store.store_website_checks(checks)
                        logger.info(f"Stored {len(checks)} website accessibility checks")
                    else:
                        logger.warning("No website checks generated")
                except Exception as e:
                    logger.error(f"Module 6 (Website Accessibility) failed: {e}", exc_info=True)
            else:
                logger.info("Module 6 (Website Accessibility) skipped (disabled in config)")

            # Step 3: Citations (Module 5)
            deduplicator = CitationDeduplicator(conn)
            citations = deduplicator.process_citations_from_run(run_id)
            if citations:
                self.store.save_citations(citations)
            logger.info(f"Deduplicated {len(citations)} citations")

            # Step 4: Gaps (Module 8)
            detector = GapDetector(conn)
            gaps = detector.detect_all_gaps(run_id)
            for gap in gaps:
                self.store.save_gap(gap)
            logger.info(f"Detected {len(gaps)} gaps")

            # Step 5: Recommendations (Module 9)
            # Use ClaudeEngine for LLM-based recommendations if available
            recommendation_engine = None
            if self.engine.name == "claude":
                recommendation_engine = self.engine
            else:
                # For non-Claude engines, try to create a Claude engine for recommendations
                try:
                    from aeo_eval.engine.claude_engine import ClaudeEngine
                    recommendation_engine = ClaudeEngine(self.config)
                except Exception as e:
                    logger.info(f"Could not initialize ClaudeEngine for recommendations: {e}")

            generator = RecommendationGenerator(conn, engine=recommendation_engine)
            recommendations = generator.generate_for_run(run_id)

            num_auto_approved = 0
            for rec in recommendations:
                self.store.save_recommendation(rec)

                # Step 6: Auto-approve if criteria met (high priority + high confidence)
                if should_auto_approve(rec):
                    self.store.update_recommendation_status(
                        rec["id"],
                        "approved",
                        approved_by="system",
                        review_notes="Auto-approved: high priority + high confidence",
                    )
                    num_auto_approved += 1

            logger.info(
                f"Generated {len(recommendations)} recommendations "
                f"({num_auto_approved} auto-approved)"
            )
        finally:
            conn.close()

        return {
            "run_id": run_id,
            "num_prompts": len(prompts),
            "num_gaps": len(gaps),
            "num_recommendations": len(recommendations),
            "num_auto_approved": num_auto_approved,
        }
