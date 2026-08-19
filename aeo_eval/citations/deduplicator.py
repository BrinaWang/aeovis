"""Citation deduplication and aggregation."""

from __future__ import annotations

from typing import Dict, List
from datetime import datetime
import logging

from aeo_eval.citations.normalizer import normalize_url, extract_domain
from aeo_eval.citations.classifier import classify_source

logger = logging.getLogger(__name__)


class CitationDeduplicator:
    """Deduplicate and classify citations."""

    def __init__(self, db_conn):
        """Initialize with database connection."""
        self.conn = db_conn

    def process_citations_from_run(self, run_id: str) -> List[Dict]:
        """
        Extract and deduplicate citations from all responses in a run.

        Args:
            run_id: ID of evaluation_runs record

        Returns:
            List of deduplicated citation dicts
        """
        cursor = self.conn.execute(
            """
            SELECT ra.id, ra.citations
            FROM response_analysis ra
            JOIN raw_responses rr ON ra.raw_response_id = rr.id
            WHERE rr.run_id = ?
            """,
            (run_id,),
        )

        import json

        deduped: Dict[str, Dict] = {}
        for analysis_id, citations_json in cursor.fetchall():
            if not citations_json:
                continue
            citations = (
                json.loads(citations_json)
                if isinstance(citations_json, str)
                else citations_json
            )
            for url in citations:
                if not url:
                    continue
                normalized = normalize_url(url)
                entry = deduped.get(normalized)
                if entry is None:
                    domain = extract_domain(normalized)
                    deduped[normalized] = {
                        "original_url": url,
                        "normalized_url": normalized,
                        "domain": domain,
                        "source_category": classify_source(url, domain),
                        "occurrence_count": 1,
                        "first_observed": datetime.now().isoformat(),
                        "last_observed": datetime.now().isoformat(),
                        "occurrences": [analysis_id],
                    }
                else:
                    entry["occurrence_count"] += 1
                    entry["last_observed"] = datetime.now().isoformat()
                    entry["occurrences"].append(analysis_id)

        return list(deduped.values())
