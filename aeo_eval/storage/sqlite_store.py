from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Dict, Optional
import json

from aeo_eval.models.result import RunResult, EvaluationRun
from aeo_eval.models.analysis import ResponseAnalysisOutput

MEMORY_SENTINEL = ":memory:"
# A *named* shared-cache in-memory database. Plain ":memory:" gives every
# sqlite3.connect() call its own private, isolated database, but this
# store (and callers like the pipeline orchestrator) open a fresh
# connection per method call, so a plain ":memory:" target would silently
# lose all data between calls. The shared-cache URI form makes every
# connection see the same in-memory database for as long as at least one
# connection to it remains open somewhere in the process.
SHARED_MEMORY_URI = "file::memory:?cache=shared"


def resolve_sqlite_target(db_path: str | Path) -> tuple[str, bool]:
    """Resolve a configured db_path into a sqlite3.connect() target.

    Returns a (target, uri) tuple suitable for ``sqlite3.connect(target,
    uri=uri)``. ``:memory:`` is special-cased to a named shared-cache
    in-memory database (see SHARED_MEMORY_URI); any other path is treated
    as a real file path and its parent directory is created if needed.
    """
    if str(db_path) == MEMORY_SENTINEL:
        return SHARED_MEMORY_URI, True

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path), False


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path, self._uri = resolve_sqlite_target(db_path)
        self._schema_path = Path(__file__).parent / "sqlite_schema.sql"

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to this store's target database."""
        return sqlite3.connect(self.db_path, uri=self._uri)

    def init_db(self) -> None:
        """Initialize the database by loading schema from sqlite_schema.sql."""
        with self._connect() as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # Load and execute schema file
            if self._schema_path.exists():
                schema = self._schema_path.read_text()
                conn.executescript(schema)
            else:
                # Fallback: create minimal legacy tables for backward compatibility
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY,
                        prompt_id TEXT,
                        engine TEXT,
                        model TEXT,
                        status TEXT,
                        response_text TEXT,
                        error TEXT,
                        latency_ms INTEGER,
                        estimated_cost REAL
                    )
                    """
                )
            conn.commit()

    def apply_retention(self) -> Dict[str, int]:
        """Delete rows older than their data_retention_policy window.

        Children are purged before parents to satisfy foreign keys:
        citation_occurrences reference both response_analysis and
        citations; response_analysis references raw_responses. Tables
        with a NULL retention (metrics, gaps, recommendations) are
        never touched. Returns rows deleted per table.
        """
        deleted: Dict[str, int] = {}
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            policies = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT table_name, retention_days FROM data_retention_policy"
                ).fetchall()
                if row[1] is not None
            }

            def modifier(days):
                return f"-{int(days)} days"

            # 1. citation_occurrences referencing expiring analyses,
            #    analyses of expiring raw responses, or expiring citations.
            ra_days = policies.get("response_analysis")
            if ra_days is not None:
                conn.execute(
                    "DELETE FROM citation_occurrences WHERE response_analysis_id IN "
                    "(SELECT id FROM response_analysis WHERE created_at < datetime('now', ?))",
                    (modifier(ra_days),),
                )
            rr_days = policies.get("raw_responses")
            if rr_days is not None:
                conn.execute(
                    "DELETE FROM citation_occurrences WHERE response_analysis_id IN "
                    "(SELECT ra.id FROM response_analysis ra "
                    " JOIN raw_responses rr ON ra.raw_response_id = rr.id "
                    " WHERE rr.created_at < datetime('now', ?))",
                    (modifier(rr_days),),
                )
                # analyses attached to expiring raw responses go too,
                # even if the analysis row itself is younger. Track this
                # cascade's rowcount now, since these rows will already be
                # gone by the time the counting loop below deletes by the
                # response_analysis table's own retention window.
                cur = conn.execute(
                    "DELETE FROM response_analysis WHERE raw_response_id IN "
                    "(SELECT id FROM raw_responses WHERE created_at < datetime('now', ?))",
                    (modifier(rr_days),),
                )
                deleted["response_analysis"] = deleted.get("response_analysis", 0) + cur.rowcount
            c_days = policies.get("citations")
            if c_days is not None:
                # Purge by last_observed, not created_at: save_citations'
                # upsert deliberately never refreshes created_at on repeat
                # citations (only last_observed/occurrence_count), so a
                # continuously-cited page would otherwise be purged (and
                # its recent citation_occurrences cascade-deleted with it)
                # at the created_at retention boundary even though it was
                # cited again recently.
                conn.execute(
                    "DELETE FROM citation_occurrences WHERE citation_id IN "
                    "(SELECT id FROM citations WHERE last_observed < datetime('now', ?))",
                    (modifier(c_days),),
                )

            # 2. The policy tables themselves, children before parents.
            # citations is purged by last_observed (see comment above);
            # every other table is purged by created_at.
            date_column = {"citations": "last_observed"}
            for table in (
                "response_analysis",
                "crawler_logs",
                "website_checks",
                "citations",
                "raw_responses",
            ):
                days = policies.get(table)
                if days is None:
                    continue
                column = date_column.get(table, "created_at")
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE {column} < datetime('now', ?)",
                    (modifier(days),),
                )
                deleted[table] = deleted.get(table, 0) + cur.rowcount
            conn.commit()
        return deleted

    def save_run(self, result: RunResult) -> None:
        """Save a single evaluation result to raw_responses table.

        Creates an evaluation_runs record if needed, then inserts the response.

        Args:
            result: RunResult object containing evaluation execution data
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")

            # Ensure evaluation_runs record exists
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluation_runs
                (run_id, timestamp, engine, model, num_prompts, status)
                VALUES (?, datetime('now'), ?, ?, 1, ?)
                """,
                (result.run_batch_id, result.engine, result.model, result.status),
            )

            # Insert into raw_responses table
            conn.execute(
                """
                INSERT INTO raw_responses
                (id, run_id, prompt_id, engine, response_text, input_tokens, output_tokens,
                 cost, latency_ms, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.run_batch_id,
                    result.prompt_id,
                    result.engine,
                    result.response_text,
                    result.input_tokens,
                    result.output_tokens,
                    result.actual_cost,
                    result.latency_ms,
                    result.status,
                    result.error,
                ),
            )
            conn.commit()

    def save_runs(self, results: Iterable[RunResult]) -> None:
        """Save multiple evaluation results in batch.

        Args:
            results: Iterable of RunResult objects
        """
        for result in results:
            self.save_run(result)

    def save_evaluation_run(self, run: EvaluationRun) -> None:
        """Upsert the batch-level summary row with real totals.

        save_run() creates a minimal placeholder row per batch via
        INSERT OR IGNORE; this overwrites it with the true totals once
        the batch finishes.
        """
        status = (
            "completed" if run.prompts_failed == 0
            else ("failed" if run.prompts_succeeded == 0 else "partial_failure")
        )
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO evaluation_runs
                (run_id, timestamp, engine, model, num_prompts, filters,
                 status, cost, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    timestamp = excluded.timestamp,
                    num_prompts = excluded.num_prompts,
                    filters = excluded.filters,
                    status = excluded.status,
                    cost = excluded.cost,
                    duration_seconds = excluded.duration_seconds
                """,
                (
                    run.run_id,
                    run.run_timestamp.isoformat(),
                    run.engine,
                    run.model_version,
                    run.prompts_run,
                    json.dumps(run.filters_applied),
                    status,
                    run.total_cost,
                    int(run.duration_seconds),
                ),
            )
            conn.commit()

    def save_analysis(self, analysis: ResponseAnalysisOutput) -> None:
        """Save a single response analysis result.

        Args:
            analysis: ResponseAnalysisOutput object containing analysis data
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO response_analysis
                (id, raw_response_id, striim_mentioned, striim_recommended, striim_position,
                 brands_found, claims, citations, extraction_confidence, flagged_for_review)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"analysis-{analysis.raw_response_id}",
                    analysis.raw_response_id,
                    1 if analysis.striim_mentioned else 0,
                    1 if analysis.striim_recommended else 0,
                    analysis.striim_position,
                    analysis.brands_found,
                    analysis.claims,
                    analysis.citations,
                    analysis.extraction_confidence,
                    1 if analysis.flagged_for_review else 0,
                ),
            )
            conn.commit()

    def save_batch_analyses(self, analyses: List[ResponseAnalysisOutput]) -> None:
        """Save multiple response analyses in a single transaction.

        Args:
            analyses: List of ResponseAnalysisOutput objects
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                for analysis in analyses:
                    conn.execute(
                        """
                        INSERT INTO response_analysis
                        (id, raw_response_id, striim_mentioned, striim_recommended, striim_position,
                         brands_found, claims, citations, extraction_confidence, flagged_for_review)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"analysis-{analysis.raw_response_id}",
                            analysis.raw_response_id,
                            1 if analysis.striim_mentioned else 0,
                            1 if analysis.striim_recommended else 0,
                            analysis.striim_position,
                            analysis.brands_found,
                            analysis.claims,
                            analysis.citations,
                            analysis.extraction_confidence,
                            1 if analysis.flagged_for_review else 0,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_raw_responses_by_batch(self, run_batch_id: str) -> List[Dict]:
        """Fetch all raw responses for a given batch.

        Args:
            run_batch_id: The run_id to filter by

        Returns:
            List of dictionaries with raw response data
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, run_id, prompt_id, engine, response_text, input_tokens, output_tokens,
                       cost, latency_ms, status, error, created_at
                FROM raw_responses
                WHERE run_id = ?
                ORDER BY created_at DESC
                """,
                (run_batch_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_analysis_by_batch(self, run_batch_id: str) -> List[Dict]:
        """Fetch all response analyses for a given batch.

        Args:
            run_batch_id: The run_id to filter by

        Returns:
            List of dictionaries with analysis data
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ra.id, ra.raw_response_id, ra.striim_mentioned, ra.striim_recommended,
                       ra.striim_position, ra.brands_found, ra.claims, ra.citations,
                       ra.extraction_confidence, ra.flagged_for_review, ra.created_at
                FROM response_analysis ra
                INNER JOIN raw_responses rr ON ra.raw_response_id = rr.id
                WHERE rr.run_id = ?
                ORDER BY ra.created_at DESC
                """,
                (run_batch_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_batch_metadata(self, run_batch_id: str) -> Dict[str, Dict]:
        """Fetch metadata for a batch including run info and stats.

        Args:
            run_batch_id: The run_id to fetch metadata for

        Returns:
            Dictionary with batch metadata
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get evaluation run metadata
            cursor.execute(
                """
                SELECT run_id, timestamp, engine, model, num_prompts, filters, status,
                       cost, duration_seconds, created_at
                FROM evaluation_runs
                WHERE run_id = ?
                """,
                (run_batch_id,),
            )
            run_row = cursor.fetchone()

            if not run_row:
                return {}

            # Get stats
            cursor.execute(
                "SELECT COUNT(*) as raw_response_count FROM raw_responses WHERE run_id = ?",
                (run_batch_id,),
            )
            response_count = cursor.fetchone()["raw_response_count"]

            cursor.execute(
                """
                SELECT COUNT(*) as analysis_count FROM response_analysis ra
                INNER JOIN raw_responses rr ON ra.raw_response_id = rr.id
                WHERE rr.run_id = ?
                """,
                (run_batch_id,),
            )
            analysis_count = cursor.fetchone()["analysis_count"]

            return {
                "run": dict(run_row),
                "raw_responses_count": response_count,
                "analyses_count": analysis_count,
            }

    def save_prompts(self, prompts: Iterable) -> None:
        """Upsert prompt catalog metadata (id, topic, persona, priority, ...).

        This lets run-scoped queries (e.g. Module 4's by-topic metrics
        breakdown) join ``raw_responses.prompt_id`` against topic/persona
        metadata. Safe to call repeatedly; existing rows are updated
        in place rather than duplicated.

        Args:
            prompts: Iterable of Prompt objects (aeo_eval.models.prompt.Prompt)
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for prompt in prompts:
                conn.execute(
                    """
                    INSERT INTO prompts (id, prompt_text, topic, persona, intent, priority, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        prompt_text = excluded.prompt_text,
                        topic = excluded.topic,
                        persona = excluded.persona,
                        intent = excluded.intent,
                        priority = excluded.priority,
                        enabled = excluded.enabled
                    """,
                    (
                        prompt.id,
                        prompt.prompt,
                        prompt.topic,
                        prompt.persona,
                        prompt.intent,
                        prompt.priority,
                        1 if prompt.enabled else 0,
                    ),
                )
            conn.commit()

    def save_metrics(self, run_id: str, metrics: Dict) -> None:
        """Save visibility metrics."""
        import json
        import uuid

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO visibility_metrics
                (id, run_id, dimension, dimension_value,
                 striim_mention_rate, striim_recommendation_rate, striim_top3_rate,
                 striim_avg_position, striim_citation_rate,
                 competitor_mention_rates, num_responses)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    metrics.get("dimension", "overall"),
                    metrics.get("dimension_value"),
                    metrics.get("mention_rate", 0.0),
                    metrics.get("recommendation_rate", 0.0),
                    metrics.get("top3_rate", 0.0),
                    metrics.get("avg_position"),
                    metrics.get("citation_rate", 0.0),
                    json.dumps(metrics.get("competitor_mention_rates", {})),
                    metrics.get("num_responses", 0),
                ),
            )
            conn.commit()

    def save_citations(self, citations: List[Dict]) -> None:
        """Upsert deduplicated citations and record per-response occurrences.

        Upserting by normalized_url preserves the original row id and
        first_observed while accumulating occurrence_count, so citation
        history survives across runs (the old INSERT OR REPLACE wiped it).
        """
        import uuid

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for citation in citations:
                conn.execute(
                    """
                    INSERT INTO citations
                    (id, url, normalized_url, domain, source_category,
                     first_observed, last_observed, occurrence_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(normalized_url) DO UPDATE SET
                        last_observed = excluded.last_observed,
                        occurrence_count = citations.occurrence_count + excluded.occurrence_count
                    """,
                    (
                        str(uuid.uuid4()),
                        citation.get("original_url", ""),
                        citation["normalized_url"],
                        citation["domain"],
                        citation["source_category"],
                        citation["first_observed"],
                        citation["last_observed"],
                        citation["occurrence_count"],
                    ),
                )
                citation_id = conn.execute(
                    "SELECT id FROM citations WHERE normalized_url = ?",
                    (citation["normalized_url"],),
                ).fetchone()[0]
                for analysis_id in citation.get("occurrences", []):
                    conn.execute(
                        """
                        INSERT INTO citation_occurrences
                        (id, citation_id, response_analysis_id)
                        VALUES (?, ?, ?)
                        """,
                        (str(uuid.uuid4()), citation_id, analysis_id),
                    )
            conn.commit()

    def save_gap(self, gap: Dict) -> None:
        """Save a detected gap."""
        import json

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO gaps
                (id, topic, gap_type, striim_visibility, top_competitor_visibility,
                 top_competitor_name, affected_prompts, evidence_ids, priority,
                 confidence, run_id, created_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    gap["id"],
                    gap["topic"],
                    gap["gap_type"],
                    gap["striim_visibility"],
                    gap["top_competitor_visibility"],
                    gap.get("top_competitor_name", "Unknown"),
                    json.dumps(gap.get("affected_prompts", [])),
                    json.dumps(gap.get("evidence_ids", [])),
                    gap["priority"],
                    gap["confidence"],
                    gap["run_id"],
                    gap["created_timestamp"],
                ),
            )
            conn.commit()

    def save_recommendation(self, recommendation: Dict) -> None:
        """Save a recommendation."""
        import json

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO recommendations
                (id, gap_id, problem, evidence_summary, recommended_action,
                 affected_pages, suggested_owner, priority, estimated_effort,
                 measurement_plan, confidence, status, created_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation["id"],
                    recommendation["gap_id"],
                    recommendation["problem"],
                    recommendation["evidence_summary"],
                    recommendation["recommended_action"],
                    json.dumps(recommendation.get("affected_pages", [])),
                    recommendation["suggested_owner"],
                    recommendation["priority"],
                    recommendation["estimated_effort"],
                    recommendation["measurement_plan"],
                    recommendation["confidence"],
                    recommendation["status"],
                    recommendation["created_timestamp"],
                ),
            )
            conn.commit()

    def update_recommendation_status(
        self,
        recommendation_id: str,
        status: str,
        approved_by: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> None:
        """Update recommendation status and approval fields."""
        import json
        from datetime import datetime

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                UPDATE recommendations
                SET status = ?, approved_by = ?, approval_timestamp = ?, review_notes = ?
                WHERE id = ?
                """,
                (
                    status,
                    approved_by,
                    datetime.now().isoformat() if approved_by else None,
                    json.dumps(review_notes) if review_notes else None,
                    recommendation_id,
                ),
            )
            conn.commit()
