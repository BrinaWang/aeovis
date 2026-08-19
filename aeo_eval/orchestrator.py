"""Full pipeline orchestration.

Wires together the answer-engine runner (Module 2), response analysis
extraction (Module 3, integrated into the evaluator), visibility metrics
(Module 4), citation deduplication (Module 5), gap detection (Module 8),
and recommendation generation with auto-approval (Module 9) into a single
top-level entry point.
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

logger = logging.getLogger(__name__)


class AEOPipelineOrchestrator:
    """Orchestrate the full AEO evaluation pipeline.

    This is the top-level entry point for running prompts end-to-end:
    answer engine -> analysis -> metrics -> citations -> gaps ->
    recommendations -> auto-approval. Callers (e.g. the CLI) should use
    this instead of driving ``Evaluator`` directly.
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
        3. Calculate visibility metrics
        4. Deduplicate and classify citations
        5. Detect gaps
        6. Generate recommendations
        7. Auto-approve high-confidence recommendations

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
            generator = RecommendationGenerator(conn)
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
