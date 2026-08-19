"""Calculate visibility metrics from response analysis."""

from __future__ import annotations

from typing import Dict, Optional
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def has_striim_citation(citations_json) -> bool:
    """True when the response's citation list includes a striim.com URL."""
    if not citations_json:
        return False
    citations = (
        json.loads(citations_json)
        if isinstance(citations_json, str)
        else citations_json
    )
    return any(
        isinstance(url, str) and "striim.com" in url.lower()
        for url in citations
    )


class MetricsCalculator:
    """Calculate visibility metrics from evaluation runs."""

    def __init__(self, db_conn):
        """Initialize with database connection."""
        self.conn = db_conn

    def calculate_metrics_for_run(self, run_id: str) -> Dict:
        """
        Calculate all visibility metrics for a completed run.

        Args:
            run_id: ID of evaluation_runs record

        Returns:
            Dict with mention_rate, recommendation_rate, top3_rate, avg_position, citation_rate, etc.
        """
        # Query response_analysis for this run
        cursor = self.conn.execute(
            """
            SELECT
                ra.striim_mentioned,
                ra.striim_recommended,
                ra.striim_position,
                ra.brands_found,
                ra.citations,
                rr.prompt_id
            FROM response_analysis ra
            JOIN raw_responses rr ON ra.raw_response_id = rr.id
            WHERE rr.run_id = ?
            """,
            (run_id,),
        )

        rows = cursor.fetchall()

        if not rows:
            logger.warning(f"No analysis records found for run {run_id}")
            return {}

        total_responses = len(rows)
        striim_mentions = 0
        striim_recommendations = 0
        striim_citing_responses = 0
        positions = []
        competitor_counts: Dict[str, int] = {}

        for row in rows:
            mentioned, recommended, position, brands_json, citations_json, prompt_id = row

            if mentioned:
                striim_mentions += 1

            if recommended:
                striim_recommendations += 1

            if position is not None and position > 0:
                positions.append(position)

            if has_striim_citation(citations_json):
                striim_citing_responses += 1

            if brands_json:
                brands = json.loads(brands_json) if isinstance(brands_json, str) else brands_json
                for brand in brands:
                    if brand != "Striim":
                        competitor_counts[brand] = competitor_counts.get(brand, 0) + 1

        mention_rate = striim_mentions / total_responses if total_responses > 0 else 0.0
        top3_rate = len([p for p in positions if p <= 3]) / total_responses if total_responses > 0 else 0.0
        avg_position = sum(positions) / len(positions) if positions else None
        citation_rate = striim_citing_responses / total_responses if total_responses > 0 else 0.0
        competitor_mention_rates = {
            brand: count / total_responses
            for brand, count in competitor_counts.items()
        }

        return {
            "mention_rate": mention_rate,
            "recommendation_rate": striim_recommendations / total_responses if total_responses > 0 else 0.0,
            "top3_rate": top3_rate,
            "avg_position": avg_position,
            "citation_rate": citation_rate,
            "competitor_mention_rates": competitor_mention_rates,
            "num_responses": total_responses,
            "dimension": "overall",
            "dimension_value": None,
        }

    def calculate_metrics_by_topic(self, run_id: str) -> list[Dict]:
        """
        Calculate metrics broken down by topic.

        Args:
            run_id: ID of evaluation_runs record

        Returns:
            List of metric dicts, one per topic
        """
        cursor = self.conn.execute(
            """
            SELECT DISTINCT p.topic
            FROM response_analysis ra
            JOIN raw_responses rr ON ra.raw_response_id = rr.id
            JOIN prompts p ON rr.prompt_id = p.id
            WHERE rr.run_id = ?
            """,
            (run_id,),
        )

        topics = [row[0] for row in cursor.fetchall()]
        results = []

        for topic in topics:
            cursor = self.conn.execute(
                """
                SELECT
                    ra.striim_mentioned,
                    ra.striim_recommended,
                    ra.striim_position,
                    ra.citations,
                    ra.brands_found
                FROM response_analysis ra
                JOIN raw_responses rr ON ra.raw_response_id = rr.id
                JOIN prompts p ON rr.prompt_id = p.id
                WHERE rr.run_id = ? AND p.topic = ?
                """,
                (run_id, topic),
            )

            rows = cursor.fetchall()
            total = len(rows)
            striim_mentions = sum(1 for r in rows if r[0])
            striim_recommendations = sum(1 for r in rows if r[1])
            striim_citing = sum(1 for r in rows if has_striim_citation(r[3]))
            positions = [r[2] for r in rows if r[2] and r[2] > 0]

            competitor_counts: Dict[str, int] = {}
            for r in rows:
                brands_json = r[4]
                if not brands_json:
                    continue
                brands = json.loads(brands_json) if isinstance(brands_json, str) else brands_json
                for brand in brands:
                    if brand != "Striim":
                        competitor_counts[brand] = competitor_counts.get(brand, 0) + 1

            competitor_mention_rates = {
                brand: count / total if total > 0 else 0.0
                for brand, count in competitor_counts.items()
            }

            results.append({
                "mention_rate": striim_mentions / total if total > 0 else 0.0,
                "recommendation_rate": striim_recommendations / total if total > 0 else 0.0,
                "top3_rate": len([p for p in positions if p <= 3]) / total if total > 0 else 0.0,
                "avg_position": sum(positions) / len(positions) if positions else None,
                "citation_rate": striim_citing / total if total > 0 else 0.0,
                "competitor_mention_rates": competitor_mention_rates,
                "num_responses": total,
                "dimension": "by_topic",
                "dimension_value": topic,
            })

        return results
