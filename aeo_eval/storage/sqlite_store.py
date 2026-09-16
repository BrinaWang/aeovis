from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from typing import Iterable, List, Dict, Optional
from datetime import datetime, timedelta
import json

from aeo_eval.models.result import RunResult, EvaluationRun
from aeo_eval.models.analysis import ResponseAnalysisOutput

logger = logging.getLogger(__name__)

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


def _json_field(value):
    """Serialize a structured column value for SQLite.

    Lists/dicts are stored as JSON text (the read path json.loads them
    back). None passes through as NULL, and an already-serialized string
    is stored as-is so callers can pass either form.
    """
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


def _parse_json_field(record: Dict, key: str) -> None:
    """Deserialize a JSON column in place, leaving non-JSON values as-is."""
    if record.get(key):
        try:
            record[key] = json.loads(record[key])
        except (json.JSONDecodeError, TypeError):
            pass


_RECOMMENDATION_INSERT = """
    INSERT INTO recommendations
    (id, gap_id, problem, evidence_summary, recommended_action,
     affected_pages, suggested_owner, priority, estimated_effort,
     measurement_plan, confidence, status, platform,
     implementation_steps, templates_applied, created_timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _recommendation_row(recommendation: Dict) -> tuple:
    """Parameter tuple for _RECOMMENDATION_INSERT.

    The optional columns (platform, implementation_steps,
    templates_applied) bind NULL when absent; apply_schema_migrations
    guarantees they exist on any database init_db has touched.
    """
    return (
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
        recommendation.get("platform"),
        _json_field(recommendation.get("implementation_steps")),
        _json_field(recommendation.get("templates_applied")),
        recommendation["created_timestamp"],
    )


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path, self._uri = resolve_sqlite_target(db_path)
        self._schema_path = Path(__file__).parent / "sqlite_schema.sql"

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to this store's target database."""
        return sqlite3.connect(self.db_path, uri=self._uri)

    def init_db(self) -> None:
        """Initialize the database by loading schema from sqlite_schema.sql."""
        # Apply migrations FIRST to add any missing columns to existing tables
        # This prevents schema script from failing on indexes for non-existent columns
        self.apply_schema_migrations()

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

    def apply_schema_migrations(self) -> bool:
        """Add columns to existing tables that the schema script can't.

        All CREATE TABLE/INDEX DDL lives in sqlite_schema.sql (idempotent
        via IF NOT EXISTS); the only work the schema script cannot do is
        ALTER an existing table. This must run before the schema script so
        its indexes on the new columns don't fail on an old database.

        Returns:
            True if migration succeeded, False otherwise
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute("PRAGMA table_info(recommendations)")
                existing_columns = {row[1] for row in cursor.fetchall()}
                if not existing_columns:
                    # Fresh database: the schema script creates the table
                    # with every column already in place.
                    return True

                columns_to_add = {
                    "platform": "TEXT",
                    "implementation_steps": "TEXT",
                    "templates_applied": "TEXT",
                }

                for col_name, col_type in columns_to_add.items():
                    if col_name not in existing_columns:
                        conn.execute(
                            f"ALTER TABLE recommendations ADD COLUMN {col_name} {col_type}"
                        )
                        logger.info(f"Added column {col_name} to recommendations table")

                conn.commit()
                return True

        except sqlite3.Error as e:
            logger.error(f"Error applying schema migrations: {e}")
            return False

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
        """Save a recommendation.

        Args:
            recommendation: Recommendation dict with keys:
                - id, gap_id, problem, evidence_summary, recommended_action,
                  affected_pages, suggested_owner, priority, estimated_effort,
                  measurement_plan, confidence, status, created_timestamp
                - Optional: platform, implementation_steps, templates_applied
        """
        self.save_recommendations([recommendation])

    def save_recommendations(self, recommendations: List[Dict]) -> None:
        """Save multiple recommendations in a single transaction.

        Args:
            recommendations: List of recommendation dicts (can include optional
                platform, implementation_steps, templates_applied fields)
        """
        if not recommendations:
            return

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.executemany(
                    _RECOMMENDATION_INSERT,
                    [_recommendation_row(rec) for rec in recommendations],
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

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

    def get_recommendation(self, rec_id: str) -> Optional[Dict]:
        """Fetch a single recommendation with all details.

        Args:
            rec_id: The recommendation ID to fetch

        Returns:
            Dictionary with recommendation details, or None if not found
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, gap_id, problem, evidence_summary, recommended_action,
                       affected_pages, suggested_owner, priority, estimated_effort,
                       measurement_plan, confidence, status, created_by, approved_by,
                       approval_timestamp, review_notes, platform, implementation_steps,
                       templates_applied, created_timestamp, created_at
                FROM recommendations
                WHERE id = ?
                """,
                (rec_id,),
            )
            row = cursor.fetchone()
            if row:
                rec_dict = dict(row)
                for key in ("affected_pages", "review_notes",
                            "implementation_steps", "templates_applied"):
                    _parse_json_field(rec_dict, key)
                return rec_dict
            return None

    def update_recommendation(self, rec_id: str, updates: dict) -> bool:
        """Update recommendation with provided fields.

        Updates any of: problem, recommended_action, priority, estimated_effort,
        status, review_notes. Uses transactions with proper error handling.

        Args:
            rec_id: The recommendation ID to update
            updates: Dictionary of fields to update (can include any recommendation field)

        Returns:
            True if successful, False otherwise
        """
        if not updates:
            logger.warning(f"No updates provided for recommendation {rec_id}")
            return False

        # Allowed fields that can be updated
        allowed_fields = {
            "problem", "recommended_action", "priority", "estimated_effort",
            "status", "review_notes", "suggested_owner", "measurement_plan",
            "confidence", "affected_pages"
        }

        # Filter updates to only allowed fields
        safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}

        if not safe_updates:
            logger.warning(f"No valid update fields provided for recommendation {rec_id}")
            return False

        try:
            with self._connect() as conn:
                conn.execute("PRAGMA foreign_keys = ON")

                # Build dynamic UPDATE statement
                set_clauses = [f"{field} = ?" for field in safe_updates.keys()]
                set_string = ", ".join(set_clauses)
                values = list(safe_updates.values())
                values.append(rec_id)

                sql = f"""
                    UPDATE recommendations
                    SET {set_string}
                    WHERE id = ?
                """

                cursor = conn.execute(sql, values)
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Updated recommendation {rec_id} with fields: {list(safe_updates.keys())}")
                    return True
                else:
                    logger.warning(f"No recommendation found with ID {rec_id}")
                    return False

        except Exception as e:
            logger.error(f"Error updating recommendation {rec_id}: {e}")
            return False

    def approve_recommendation(self, rec_id: str, approved_by: str) -> bool:
        """Mark a recommendation as approved.

        Sets status to 'approved', sets approval_timestamp to now, and records
        the approver.

        Args:
            rec_id: The recommendation ID to approve
            approved_by: The identifier of who is approving (user, email, etc.)

        Returns:
            True if successful, False otherwise
        """
        from datetime import datetime

        try:
            with self._connect() as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                now = datetime.now().isoformat()

                cursor = conn.execute(
                    """
                    UPDATE recommendations
                    SET status = ?, approved_by = ?, approval_timestamp = ?
                    WHERE id = ?
                    """,
                    ("approved", approved_by, now, rec_id),
                )
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Approved recommendation {rec_id} by {approved_by}")
                    return True
                else:
                    logger.warning(f"No recommendation found with ID {rec_id}")
                    return False

        except Exception as e:
            logger.error(f"Error approving recommendation {rec_id}: {e}")
            return False

    def reject_recommendation(self, rec_id: str, review_notes: str) -> bool:
        """Mark a recommendation as rejected.

        Sets status to 'rejected' and stores review_notes explaining the rejection.

        Args:
            rec_id: The recommendation ID to reject
            review_notes: Notes explaining the rejection reason

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._connect() as conn:
                conn.execute("PRAGMA foreign_keys = ON")

                # Store review_notes as JSON
                review_data = json.dumps({"reason": review_notes}) if review_notes else None

                cursor = conn.execute(
                    """
                    UPDATE recommendations
                    SET status = ?, review_notes = ?
                    WHERE id = ?
                    """,
                    ("rejected", review_data, rec_id),
                )
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Rejected recommendation {rec_id}")
                    return True
                else:
                    logger.warning(f"No recommendation found with ID {rec_id}")
                    return False

        except Exception as e:
            logger.error(f"Error rejecting recommendation {rec_id}: {e}")
            return False

    def store_website_checks(self, records: List[Dict]) -> int:
        """Store website accessibility check results.

        Args:
            records: List of check records with keys matching website_checks table:
                - id: Unique identifier
                - run_id: Evaluation run ID
                - striim_url: The URL checked
                - crawler: Crawler user-agent
                - robots_allowed: Boolean (0/1)
                - in_sitemap: Boolean (0/1) or None
                - http_status: HTTP status code or None
                - response_time_ms: Response time in milliseconds or None
                - noindex: Boolean (0/1)
                - canonical_url: Canonical URL or None
                - result: Classification string
                - check_timestamp: ISO format timestamp

        Returns:
            Number of records inserted
        """
        if not records:
            return 0

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                data = [
                    (
                        record["id"],
                        record["run_id"],
                        record["striim_url"],
                        record["crawler"],
                        record.get("robots_allowed"),
                        record.get("in_sitemap"),
                        record.get("http_status"),
                        record.get("response_time_ms"),
                        record.get("noindex"),
                        record.get("canonical_url"),
                        record["result"],
                        record["check_timestamp"],
                    )
                    for record in records
                ]
                conn.executemany(
                    """
                    INSERT INTO website_checks
                    (id, run_id, striim_url, crawler, robots_allowed, in_sitemap,
                     http_status, response_time_ms, noindex, canonical_url,
                     result, check_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    data,
                )
                conn.commit()
                return len(records)
            except Exception as e:
                conn.rollback()
                logger.error(f"Error storing website checks: {e}")
                raise

    def store_crawler_logs(self, records: List[Dict]) -> int:
        """Store AI crawler activity from request logs.

        Args:
            records: List of crawler log records from RequestLogAnalyzer with keys:
                - id: Unique identifier
                - run_id: Evaluation run ID
                - timestamp: ISO format timestamp of the request
                - host: Request host/domain
                - path: Normalized request path
                - crawler: Identified crawler name (e.g. "oai-searchbot")
                - http_status: HTTP status code
                - response_time_ms: Response time in milliseconds or None
                - edge_action: Classification of response ("allowed", "blocked", "rate_limited", "error")
                - log_source: Source of the log (e.g. "request_log")
                - ua_classification: Dict with classifier output (not stored in DB, metadata only)

        Returns:
            Number of records inserted
        """
        if not records:
            return 0

        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                data = [
                    (
                        record.get("id"),
                        record["run_id"],
                        record.get("timestamp"),
                        record.get("host"),
                        record.get("path"),
                        record.get("crawler"),
                        record.get("http_status"),
                        record.get("response_time_ms"),
                        record.get("edge_action"),
                        record.get("log_source"),
                    )
                    for record in records
                ]
                conn.executemany(
                    """
                    INSERT INTO crawler_logs
                    (id, run_id, timestamp, host, path, crawler, http_status,
                     response_time_ms, edge_action, log_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    data,
                )
                conn.commit()
                return len(records)
            except Exception as e:
                conn.rollback()
                logger.error(f"Error storing crawler logs: {e}")
                raise

    def get_run_status_and_cost(self, run_id: str) -> tuple[Optional[str], float]:
        """Get one evaluation run's status and accumulated cost.

        Returns (None, 0.0) when the run doesn't exist.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, cost FROM evaluation_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                return None, 0.0
            return row[0], row[1] or 0.0

    def set_run_status(self, run_id: str, status: str) -> None:
        """Set one evaluation run's status."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE evaluation_runs SET status = ? WHERE run_id = ?",
                (status, run_id),
            )
            conn.commit()

    def add_to_run_cost(self, run_id: str, amount: float) -> None:
        """Add post-evaluation spend (e.g. recommendation LLM calls) to a run's total."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE evaluation_runs SET cost = COALESCE(cost, 0) + ? WHERE run_id = ?",
                (amount, run_id),
            )
            conn.commit()

    def get_total_cost_and_run_count(self) -> Dict:
        """Get total cost across all runs and number of runs."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as num_runs, SUM(cost) as total_cost
                FROM evaluation_runs
            """)
            row = cursor.fetchone()
            return {
                'num_runs': row[0] or 0,
                'total_cost': row[1] or 0.0
            }

    def get_cost_by_engine(self) -> List[Dict]:
        """Get total cost breakdown by engine."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT engine, COUNT(*) as num_runs, SUM(cost) as total_cost,
                       AVG(cost) as avg_cost, MIN(cost) as min_cost, MAX(cost) as max_cost
                FROM evaluation_runs
                GROUP BY engine
                ORDER BY total_cost DESC
            """)
            rows = cursor.fetchall()
            return [
                {
                    'engine': row[0],
                    'num_runs': row[1],
                    'total_cost': row[2] or 0.0,
                    'avg_cost': row[3] or 0.0,
                    'min_cost': row[4] or 0.0,
                    'max_cost': row[5] or 0.0
                }
                for row in rows
            ]

    def get_cost_by_topic(self) -> List[Dict]:
        """Get total cost breakdown by topic, including run-level analysis costs.

        Allocates run-level costs (which include analysis) proportionally to each topic
        based on the number of prompts in that topic within each run.
        """
        with self._connect() as conn:
            cursor = conn.cursor()

            # Get all responses with their run and topic info
            cursor.execute("""
                SELECT rr.run_id, p.topic, rr.cost, COUNT(*) OVER (PARTITION BY rr.run_id) as prompts_per_run
                FROM raw_responses rr
                JOIN prompts p ON rr.prompt_id = p.id
                JOIN evaluation_runs er ON rr.run_id = er.run_id
                WHERE p.topic IS NOT NULL
                ORDER BY rr.run_id, p.topic
            """)
            response_rows = cursor.fetchall()

            # Get run-level totals for analysis cost allocation
            cursor.execute("""
                SELECT run_id, cost
                FROM evaluation_runs
            """)
            run_costs = {row[0]: row[1] for row in cursor.fetchall()}

            # Aggregate by topic
            topic_data = {}
            for run_id, topic, engine_cost, prompts_per_run in response_rows:
                if topic not in topic_data:
                    topic_data[topic] = {
                        'runs': set(),
                        'prompts': 0,
                        'engine_cost': 0.0,
                        'run_costs': []
                    }

                topic_data[topic]['runs'].add(run_id)
                topic_data[topic]['prompts'] += 1
                topic_data[topic]['engine_cost'] += engine_cost or 0.0
                topic_data[topic]['run_costs'].append((run_id, prompts_per_run, run_costs.get(run_id, 0.0)))

            # Calculate final totals with proportionally allocated analysis costs
            results = []
            for topic, data in topic_data.items():
                total_analysis_cost = 0.0
                seen_runs = set()

                for run_id, prompts_per_run, run_total_cost in data['run_costs']:
                    if run_id not in seen_runs:
                        seen_runs.add(run_id)
                        # Get sum of engine costs for this run
                        cursor.execute(
                            "SELECT SUM(cost) FROM raw_responses WHERE run_id = ?",
                            (run_id,)
                        )
                        total_engine_cost_in_run = cursor.fetchone()[0] or 0.0
                        # Analysis cost = total run cost - total engine cost
                        analysis_cost_in_run = run_total_cost - total_engine_cost_in_run

                        # Allocate proportionally by topic
                        topic_proportion = data['prompts'] / prompts_per_run if prompts_per_run > 0 else 0
                        total_analysis_cost += analysis_cost_in_run * topic_proportion

                total_cost = data['engine_cost'] + total_analysis_cost
                avg_cost = total_cost / data['prompts'] if data['prompts'] > 0 else 0.0

                results.append({
                    'topic': topic,
                    'num_runs': len(data['runs']),
                    'total_cost': total_cost,
                    'avg_cost_per_prompt': avg_cost,
                    'num_prompts': data['prompts']
                })

            results.sort(key=lambda x: x['total_cost'], reverse=True)
            return results

    def get_all_runs_cost_detail(self) -> List[Dict]:
        """Get all runs with cost details for the cost table."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT run_id, timestamp, engine, model, num_prompts, cost, duration_seconds, status
                FROM evaluation_runs
                ORDER BY timestamp DESC
            """)
            rows = cursor.fetchall()
            return [
                {
                    'run_id': row[0],
                    'timestamp': row[1],
                    'engine': row[2],
                    'model': row[3],
                    'num_prompts': row[4],
                    'total_cost': row[5] or 0.0,
                    'duration_seconds': row[6] or 0,
                    'status': row[7],
                    'cost_per_prompt': (row[5] or 0.0) / (row[4] or 1)
                }
                for row in rows
            ]

    def get_cost_trends(self, days: int = 90) -> List[Dict]:
        """Get cost trends over time."""
        with self._connect() as conn:
            cursor = conn.cursor()
            since = (datetime.now() - timedelta(days=days)).isoformat()
            cursor.execute("""
                SELECT DATE(timestamp) as date, engine, COUNT(*) as num_runs,
                       SUM(cost) as daily_cost, AVG(cost) as avg_cost
                FROM evaluation_runs
                WHERE timestamp >= ?
                GROUP BY DATE(timestamp), engine
                ORDER BY date
            """, (since,))
            rows = cursor.fetchall()
            return [
                {
                    'date': row[0],
                    'engine': row[1],
                    'num_runs': row[2],
                    'daily_cost': row[3] or 0.0,
                    'avg_cost': row[4] or 0.0
                }
                for row in rows
            ]

    def get_today_cost(self) -> float:
        """Get total cost spent today (since midnight UTC)."""
        with self._connect() as conn:
            cursor = conn.cursor()
            today = datetime.now().date().isoformat()
            cursor.execute("""
                SELECT SUM(cost) FROM evaluation_runs
                WHERE DATE(timestamp) = ?
            """, (today,))
            result = cursor.fetchone()[0]
            return result or 0.0

    def save_recommendation_template(self, template: Dict) -> None:
        """Save a recommendation template.

        Args:
            template: Template dict with keys:
                - id: Unique identifier
                - platform: 'article', 'reddit', 'linkedin', or 'facebook'
                - template_type: 'implementation_steps', 'content_outline', or 'post_template'
                - content: JSON-serializable content structure
                - created_timestamp: ISO format timestamp
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO recommendation_templates
                (id, platform, template_type, content, created_timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    template["id"],
                    template["platform"],
                    template["template_type"],
                    _json_field(template["content"]),
                    template["created_timestamp"],
                ),
            )
            conn.commit()

    def get_recommendation_template(self, template_id: str) -> Optional[Dict]:
        """Fetch a single recommendation template.

        Args:
            template_id: The template ID to fetch

        Returns:
            Dictionary with template details, or None if not found
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, platform, template_type, content, created_timestamp, created_at
                FROM recommendation_templates
                WHERE id = ?
                """,
                (template_id,),
            )
            row = cursor.fetchone()
            if row:
                template_dict = dict(row)
                _parse_json_field(template_dict, "content")
                return template_dict
            return None

    def get_recommendation_templates(self, platform: Optional[str] = None, template_type: Optional[str] = None) -> List[Dict]:
        """Fetch recommendation templates, optionally filtered by platform and type.

        Args:
            platform: Optional platform filter ('article', 'reddit', 'linkedin', 'facebook')
            template_type: Optional template type filter ('implementation_steps', 'content_outline', 'post_template')

        Returns:
            List of template dictionaries
        """
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT id, platform, template_type, content, created_timestamp, created_at FROM recommendation_templates WHERE 1=1"
            params = []

            if platform:
                query += " AND platform = ?"
                params.append(platform)
            if template_type:
                query += " AND template_type = ?"
                params.append(template_type)

            query += " ORDER BY created_timestamp DESC"

            cursor.execute(query, params)
            templates = []
            for row in cursor.fetchall():
                template_dict = dict(row)
                _parse_json_field(template_dict, "content")
                templates.append(template_dict)
            return templates
