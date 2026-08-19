"""Gap detection logic."""

from __future__ import annotations

from typing import Dict, List, Optional
from datetime import datetime
import json
import logging
import uuid

from aeo_eval.gaps.thresholds import (
    should_flag_visibility_gap,
    calculate_gap_priority,
)

logger = logging.getLogger(__name__)


class GapDetector:
    """Detect gaps in visibility, citations, content, and authority."""

    def __init__(self, db_conn):
        """Initialize with database connection."""
        self.conn = db_conn

    def _topic_priority(self, topic: str) -> str:
        """Highest priority among the topic's prompts; Medium if unknown."""
        row = self.conn.execute(
            """
            SELECT priority FROM prompts
            WHERE topic = ? AND priority IS NOT NULL
            ORDER BY CASE LOWER(priority)
                WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT 1
            """,
            (topic,),
        ).fetchone()
        return row[0] if row else "Medium"

    def detect_visibility_gaps(self, run_id: str) -> List[Dict]:
        """
        Detect visibility gaps from metrics.

        Args:
            run_id: ID of evaluation_runs record

        Returns:
            List of gap dicts
        """
        # Get metrics by topic
        cursor = self.conn.execute(
            """
            SELECT dimension_value, striim_mention_rate, competitor_mention_rates, num_responses
            FROM visibility_metrics
            WHERE run_id = ? AND dimension = 'by_topic'
            """,
            (run_id,),
        )

        gaps = []
        for row in cursor.fetchall():
            topic, striim_rate, competitor_json, num_responses = row

            if num_responses < 3:
                # Skip if too few responses
                continue

            # Extract top competitor rate
            competitor_rates = json.loads(competitor_json) if competitor_json else {}
            top_competitor_rate = max(competitor_rates.values()) if competitor_rates else 0.0
            top_competitor_name = max(competitor_rates, key=competitor_rates.get) if competitor_rates else "Unknown"

            # Check if gap exists
            if should_flag_visibility_gap(
                striim_rate, top_competitor_rate, self._topic_priority(topic)
            ):
                priority = calculate_gap_priority(striim_rate, top_competitor_rate)

                gap = {
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "gap_type": "visibility",
                    "striim_visibility": striim_rate,
                    "top_competitor_visibility": top_competitor_rate,
                    "top_competitor_name": top_competitor_name,
                    "priority": priority,
                    "confidence": "high" if num_responses >= 10 else ("medium" if num_responses >= 5 else "low"),
                    "evidence_ids": [f"metrics-{run_id}-{topic}"],
                    "affected_prompts": [],  # Would populate from response_analysis join
                    "run_id": run_id,
                    "created_timestamp": datetime.now().isoformat(),
                }
                gaps.append(gap)

        return gaps

    def detect_citation_gaps(self, run_id: str) -> List[Dict]:
        """Detect topics where competitor pages are cited but Striim pages are not.

        Run-scoped: only citations observed in this run (via
        citation_occurrences) are considered. A gap fires when a topic
        has >= 3 competitor-owned citations and zero Striim-owned ones.
        """
        cursor = self.conn.execute(
            """
            SELECT p.topic,
                   SUM(CASE WHEN c.source_category = 'competitor' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN c.source_category = 'striim_owned' THEN 1 ELSE 0 END)
            FROM citation_occurrences co
            JOIN citations c ON co.citation_id = c.id
            JOIN response_analysis ra ON co.response_analysis_id = ra.id
            JOIN raw_responses rr ON ra.raw_response_id = rr.id
            JOIN prompts p ON rr.prompt_id = p.id
            WHERE rr.run_id = ?
            GROUP BY p.topic
            """,
            (run_id,),
        )

        gaps = []
        for topic, competitor_citations, striim_citations in cursor.fetchall():
            if striim_citations == 0 and competitor_citations >= 3:
                gaps.append({
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "gap_type": "citation",
                    "striim_visibility": 0.0,
                    "top_competitor_visibility": float(competitor_citations),
                    "top_competitor_name": "Competitor",
                    "priority": "high" if competitor_citations > 5 else "medium",
                    "confidence": "high" if competitor_citations > 5 else "medium",
                    "evidence_ids": [f"citations-{run_id}-{topic}"],
                    "affected_prompts": [],
                    "run_id": run_id,
                    "created_timestamp": datetime.now().isoformat(),
                })
        return gaps

    def detect_all_gaps(self, run_id: str) -> List[Dict]:
        """Detect all gap types for a run."""
        all_gaps = []
        all_gaps.extend(self.detect_visibility_gaps(run_id))
        all_gaps.extend(self.detect_citation_gaps(run_id))
        # content, technical, authority gaps deferred for now
        return all_gaps
