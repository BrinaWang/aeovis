"""Recommendation generation from gaps."""

from __future__ import annotations

from typing import Dict, Optional
from datetime import datetime
import json
import uuid
import logging

from aeo_eval.recommendations.rag import MethodsRAG

logger = logging.getLogger(__name__)

# Schema for LLM structured output - article recommendation
ARTICLE_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "article_suggestion": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "recommended_sections": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "how_it_improves_aeo": {"type": "string"},
                "source_type": {"enum": ["guide", "blog_post", "tutorial"]},
            },
            "required": ["title", "recommended_sections", "how_it_improves_aeo", "source_type"],
        },
        "recommended_action": {"type": "string"},
        "evidence_summary": {"type": "string"},
    },
    "required": ["article_suggestion", "recommended_action", "evidence_summary"],
}


class RecommendationGenerator:
    """Generate recommendations from detected gaps."""

    def __init__(self, db_conn, engine=None):
        """Initialize with database connection and optional LLM engine.

        Args:
            db_conn: Database connection
            engine: Optional BaseEngine instance for LLM-powered recommendations
        """
        self.conn = db_conn
        self.engine = engine
        self.methods_context = self._load_methods_context()
        self.rag = MethodsRAG(db_conn, engine)

        # Initialize RAG with methods if available and db_conn is valid
        if self.methods_context and self.conn:
            try:
                self.rag.initialize_methods(self.methods_context)
            except Exception as e:
                logger.warning(f"Failed to initialize RAG: {e}")

    def _load_methods_context(self) -> str:
        """Load AEO methods knowledge base from methods.txt."""
        try:
            with open("methods.txt", "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("methods.txt not found; LLM recommendations will not include methods context")
            return ""

    def _get_methods_context_for_gap(self, gap: Dict) -> str:
        """Retrieve relevant methods sections for a gap using RAG.

        Args:
            gap: Gap dict from gaps table

        Returns:
            Relevant methods sections as string, or full methods if RAG unavailable
        """
        gap_type = gap.get("gap_type", "")
        topic = gap.get("topic", "")
        striim_vis = gap.get("striim_visibility", 0)

        # Create context string for retrieval
        gap_context = f"Gap type: {gap_type}. Topic: {topic}. Visibility: {striim_vis:.0%}."

        try:
            relevant_sections = self.rag.retrieve_relevant_sections(gap_context, top_k=3)
            return "\n\n".join(relevant_sections) if relevant_sections else self.methods_context
        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}; using full methods context")
            return self.methods_context

    def _diagnose_gap_with_llm(self, gap: Dict) -> Optional[Dict]:
        """Use LLM to deeply analyze gap and diagnose root causes.

        Args:
            gap: Gap dict from gaps table

        Returns:
            Dict with diagnosis and root_causes, or None if LLM unavailable
        """
        if not self.engine:
            return None

        gap_type = gap["gap_type"]
        topic = gap["topic"]
        striim_vis = gap.get("striim_visibility", 0)
        competitor_vis = gap.get("top_competitor_visibility", 0)
        competitor_name = gap.get("top_competitor_name", "top competitor")

        # Retrieve relevant methods using RAG
        methods_context = self._get_methods_context_for_gap(gap)

        prompt = f"""Analyze this AEO visibility gap and diagnose root causes.

GAP DETAILS:
- Type: {gap_type}
- Topic: {topic}
- Striim visibility: {striim_vis:.1%}
- {competitor_name} visibility: {competitor_vis:.1%}
- Evidence sources: {len(gap.get('evidence_ids', []))}
- Affected questions: {len(gap.get('affected_prompts', []))}

RELEVANT AEO METHODS:
{methods_context}

Using only 2025-26 AEO best practices, analyze what's causing this gap. What's the likely root cause?
Consider: page organization, content depth, authority signals, technical accessibility, content recency.

Return JSON with:
- diagnosis: 1-2 sentence summary of the root cause
- root_causes: array of specific causes (e.g., "missing content sections", "low authority signals")

Focus on actionable diagnoses that point to specific improvements."""

        try:
            call = self.engine.run_with_structured_output(prompt, {
                "type": "object",
                "properties": {
                    "diagnosis": {"type": "string"},
                    "root_causes": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["diagnosis", "root_causes"]
            })
            return call.data
        except Exception as e:
            logger.warning(f"LLM diagnosis failed: {e}")
            return None

    def _generate_article_recommendation_with_llm(self, gap: Dict, diagnosis: Dict) -> Optional[Dict]:
        """Use LLM to generate article suggestion and detailed recommendation.

        Args:
            gap: Gap dict from gaps table
            diagnosis: Dict with diagnosis and root_causes from _diagnose_gap_with_llm

        Returns:
            Dict with full recommendation structure, or None if LLM unavailable
        """
        if not self.engine:
            return None

        topic = gap["topic"]
        striim_vis = gap.get("striim_visibility", 0)
        competitor_vis = gap.get("top_competitor_visibility", 0)
        competitor_name = gap.get("top_competitor_name", "top competitor")

        # Retrieve relevant methods using RAG
        methods_context = self._get_methods_context_for_gap(gap)

        prompt = f"""Generate a specific article recommendation to address this AEO gap.

DIAGNOSIS:
{diagnosis.get('diagnosis', '')}

ROOT CAUSES:
{json.dumps(diagnosis.get('root_causes', []), indent=2)}

GAP CONTEXT:
- Topic: {topic}
- Striim visibility: {striim_vis:.1%}
- {competitor_name} visibility: {competitor_vis:.1%}

RELEVANT AEO METHODS:
{methods_context}

Using only 2025-26 AEO practices, recommend:
1. A specific article Striim should create to close this gap
2. Key sections the article must include
3. Why this article will improve visibility

Return JSON with:
- article_suggestion: {{title, recommended_sections, how_it_improves_aeo, source_type}}
- recommended_action: specific action to take
- evidence_summary: brief summary of why this will work"""

        try:
            call = self.engine.run_with_structured_output(prompt, ARTICLE_RECOMMENDATION_SCHEMA)
            return call.data
        except Exception as e:
            logger.warning(f"LLM article recommendation failed: {e}")
            return None

    def generate_for_gap(self, gap: Dict) -> Dict:
        """
        Generate a recommendation for a gap using LLM analysis when available.

        Args:
            gap: Gap dict from gaps table

        Returns:
            Recommendation dict with LLM-generated content or template fallback
        """
        gap_type = gap["gap_type"]
        topic = gap["topic"]

        # Try LLM-based recommendation first
        llm_recommendation = None
        if self.engine:
            diagnosis = self._diagnose_gap_with_llm(gap)
            if diagnosis:
                llm_recommendation = self._generate_article_recommendation_with_llm(gap, diagnosis)

        # Priority 1-10 based on gap priority and visibility delta
        if gap["priority"] == "high":
            priority = 8 if gap["striim_visibility"] < 0.1 else 6
        elif gap["priority"] == "medium":
            priority = 5
        else:
            priority = 3

        confidence = gap["confidence"]
        will_auto_publish = confidence == "high" and priority >= 8
        status = "pending_publish" if will_auto_publish else "draft"

        # Use LLM recommendation if available
        if llm_recommendation and diagnosis:
            problem = (
                f"Striim appears in only {gap['striim_visibility']:.0%} of answers for '{topic}', "
                f"while {gap['top_competitor_name']} appears in {gap['top_competitor_visibility']:.0%}. "
                f"Root cause: {diagnosis.get('diagnosis', '')}"
            )
            suggested_owner = "Content Team"
            effort = 2

            article = llm_recommendation.get("article_suggestion", {})
            evidence_summary = llm_recommendation.get("evidence_summary", f"{len(gap.get('evidence_ids', []))} evidence sources")

            return {
                "id": str(uuid.uuid4()),
                "gap_id": gap["id"],
                "problem": problem,
                "evidence_summary": evidence_summary,
                "recommended_action": llm_recommendation.get("recommended_action", ""),
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
                # LLM-generated fields
                "diagnosis": diagnosis.get("diagnosis", ""),
                "root_causes": diagnosis.get("root_causes", []),
                "article_suggestion": article,
            }

        # Fallback to template-based recommendation
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
            effort = 2

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

        evidence_summary = f"{len(gap.get('evidence_ids', []))} evidence sources"

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

    def generate_for_run(self, run_id: str, use_llm: bool = True) -> list[Dict]:
        """
        Generate recommendations for all gaps in a run.

        Args:
            run_id: ID of evaluation_runs record
            use_llm: Whether to use LLM for deep gap analysis (default True if engine available)

        Returns:
            List of recommendation dicts
        """
        if not use_llm:
            self.engine = None
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
