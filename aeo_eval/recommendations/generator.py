"""Recommendation generation from gaps."""

from __future__ import annotations

from typing import Dict, Optional
from datetime import datetime
import json
import uuid
import logging

logger = logging.getLogger(__name__)


class RecommendationGenerator:
    """Generate recommendations from detected gaps."""

    def __init__(self, db_conn):
        """Initialize with database connection."""
        self.conn = db_conn

    def generate_for_gap(self, gap: Dict) -> Dict:
        """
        Generate a recommendation for a gap.

        Args:
            gap: Gap dict from gaps table

        Returns:
            Recommendation dict
        """
        gap_type = gap["gap_type"]
        topic = gap["topic"]

        # Tailor recommendation by gap type
        if gap_type == "visibility":
            problem = (
                f"Striim appears in only {gap['striim_visibility']:.0%} of answers for '{topic}', "
                f"while {gap['top_competitor_name']} appears in {gap['top_competitor_visibility']:.0%}."
            )

            recommended_action = (
                f"Create a comprehensive '{topic}' implementation guide covering: "
                "architecture, initial load, continuous CDC, schema evolution, failure recovery, "
                "security, performance methodology, and product limitations."
            )

            suggested_owner = "Content Team"
            effort = 2  # Story points

        elif gap_type == "citation":
            problem = (
                f"On '{topic}' questions, {gap['top_competitor_name']} pages are cited "
                "while relevant Striim content is not."
            )

            recommended_action = (
                f"Create or update Striim pages for '{topic}' with detailed examples, "
                "comparison to competitors, and discoverable content."
            )

            suggested_owner = "Content Team"
            effort = 2

        else:
            problem = f"Gap detected: {gap_type}"
            recommended_action = f"Investigate {gap_type} gap for '{topic}'"
            suggested_owner = "Product Manager"
            effort = 1

        # Priority 1-10 based on gap priority and visibility delta
        if gap["priority"] == "high":
            priority = 8 if gap["striim_visibility"] < 0.1 else 6
        elif gap["priority"] == "medium":
            priority = 5
        else:
            priority = 3

        # Evidence summary
        evidence_summary = f"{len(gap.get('evidence_ids', []))} evidence sources"

        # Determine if recommendation should auto-publish
        # High-confidence + high-priority (>= 8) recommendations are auto-published
        confidence = gap["confidence"]
        will_auto_publish = confidence == "high" and priority >= 8

        # Set status based on auto-publish decision
        status = "pending_publish" if will_auto_publish else "draft"

        return {
            "id": str(uuid.uuid4()),
            "gap_id": gap["id"],
            "problem": problem,
            "evidence_summary": evidence_summary,
            "recommended_action": recommended_action,
            "affected_pages": [f"https://striim.com/topic/{topic.lower()}"],
            "suggested_owner": suggested_owner,
            "priority": priority,
            "estimated_effort": effort,
            "measurement_plan": (
                f"Re-run '{topic}' questions after implementation and compare visibility metrics."
            ),
            "confidence": confidence,
            "will_auto_publish": will_auto_publish,
            "status": status,
            "created_timestamp": datetime.now().isoformat(),
        }

    def generate_for_run(self, run_id: str) -> list[Dict]:
        """
        Generate recommendations for all gaps in a run.

        Args:
            run_id: ID of evaluation_runs record

        Returns:
            List of recommendation dicts
        """
        cursor = self.conn.execute(
            """
            SELECT id, topic, gap_type, striim_visibility, top_competitor_visibility,
                   top_competitor_name, affected_prompts, evidence_ids, priority, confidence
            FROM gaps WHERE run_id = ?
            """,
            (run_id,),
        )

        gaps = []
        for row in cursor.fetchall():
            affected_prompts_json = row[6]
            affected_prompts = (
                json.loads(affected_prompts_json)
                if isinstance(affected_prompts_json, str)
                else affected_prompts_json
            )

            evidence_ids_json = row[7]
            evidence_ids = (
                json.loads(evidence_ids_json)
                if isinstance(evidence_ids_json, str)
                else evidence_ids_json
            )

            gap_dict = {
                "id": row[0],
                "topic": row[1],
                "gap_type": row[2],
                "striim_visibility": row[3],
                "top_competitor_visibility": row[4],
                "top_competitor_name": row[5],
                "affected_prompts": affected_prompts,
                "evidence_ids": evidence_ids,
                "priority": row[8],
                "confidence": row[9],
            }
            gaps.append(gap_dict)

        recommendations = []
        for gap in gaps:
            rec = self.generate_for_gap(gap)
            recommendations.append(rec)

        return recommendations
