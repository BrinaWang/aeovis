"""Recommendation generation from gaps."""

from __future__ import annotations

from typing import Dict, Optional
from datetime import datetime
import json
import uuid
import logging

from aeo_eval.recommendations.rag import MethodsRAG

logger = logging.getLogger(__name__)

# Rough prompt size for a recommendation call (gap context + run
# evidence + retrieved methods sections + instructions), used only to
# pre-check the budget.
_EST_PROMPT_TOKENS = 4000

# Caps on how much run evidence goes into a recommendation prompt, so
# prompt cost stays bounded on gaps with many affected prompts.
_EVIDENCE_MAX_QUESTIONS = 8
_EVIDENCE_MAX_RESPONSES = 5
_EVIDENCE_MAX_CITED_PAGES = 12
_EVIDENCE_EXCERPT_CHARS = 400
_EVIDENCE_MAX_CLAIMS_PER_RESPONSE = 3

# Shared instruction block appended to every recommendation prompt.
# The evidence gives the model something concrete to anchor on; these
# rules stop it from ignoring the evidence and writing boilerplate.
_SPECIFICITY_RULES = """
SPECIFICITY REQUIREMENTS (mandatory):
- Ground every claim and step in the EVIDENCE above: name the actual question, cited page, or extracted claim it addresses.
- Never write advice that could apply to any topic or any company. If a sentence would still make sense with the topic swapped out, rewrite it with the specifics.
- Every implementation step must be executable without further research: state exactly what to create or change, where it lives, and what "done" looks like.
- Do not use filler like "comprehensive guide", "best practices", "high-quality content", or "optimize for SEO" without immediately stating the concrete specifics."""

# Schema for LLM structured output - gap diagnosis.
# Every object in a structured-output schema must set
# "additionalProperties": false explicitly, or the API rejects the
# request with a 400.
GAP_DIAGNOSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "diagnosis": {"type": "string"},
        "root_causes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["diagnosis", "root_causes"],
}

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
        "implementation_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "step": {"type": "string"},
                    "effort": {"enum": ["Low", "Medium", "High"]},
                    "owner": {"enum": ["Content Team", "Product Manager", "Engineering"]},
                    "notes": {"type": "string"},
                },
                "required": ["step", "effort", "owner"],
            },
        },
    },
    "required": ["article_suggestion", "recommended_action", "evidence_summary", "implementation_steps"],
}

# Schema for LLM structured output - social media recommendation
SOCIAL_MEDIA_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recommended_action": {"type": "string"},
        "implementation_steps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "content_outline": {"type": "string"},
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "frequency": {"type": "string"},
        "evidence_summary": {"type": "string"},
    },
    "required": ["recommended_action", "implementation_steps", "content_outline", "hashtags", "frequency", "evidence_summary"],
}

# Template implementation steps used when the LLM path is unavailable.
_FALLBACK_STEPS_VISIBILITY = [
    {
        "step": "Research and gather evidence for topic coverage",
        "effort": "Medium",
        "owner": "Content Team",
        "notes": "Review competitor content, customer questions, and industry trends"
    },
    {
        "step": "Create detailed outline with key sections",
        "effort": "Low",
        "owner": "Content Team",
        "notes": "Include architecture, use cases, implementation patterns"
    },
    {
        "step": "Write draft article content",
        "effort": "High",
        "owner": "Content Team",
        "notes": "Aim for depth comparable to top competitor content"
    },
    {
        "step": "Technical review and validation",
        "effort": "Medium",
        "owner": "Product Manager",
        "notes": "Ensure accuracy and alignment with product roadmap"
    },
    {
        "step": "Peer review and refinement",
        "effort": "Low",
        "owner": "Content Team",
        "notes": "Check clarity, examples, and AEO best practices"
    },
    {
        "step": "Format and optimize for search engines",
        "effort": "Low",
        "owner": "Content Team",
        "notes": "Add metadata, internal links, structured data"
    },
    {
        "step": "Publish and monitor search visibility",
        "effort": "Low",
        "owner": "Content Team",
        "notes": "Track keyword rankings and engagement metrics"
    }
]

_FALLBACK_STEPS_CITATION = [
    {
        "step": "Identify pages cited by competitors",
        "effort": "Low",
        "owner": "Content Team",
        "notes": "Analyze search results for competing content"
    },
    {
        "step": "Create or update relevant Striim content",
        "effort": "High",
        "owner": "Content Team",
        "notes": "Ensure content is authoritative and discoverable"
    },
    {
        "step": "Build internal linking structure",
        "effort": "Medium",
        "owner": "Content Team",
        "notes": "Link from existing content to new/updated pages"
    },
    {
        "step": "Optimize for citation ranking factors",
        "effort": "Medium",
        "owner": "Product Manager",
        "notes": "Review authority signals, freshness, and relevance"
    },
    {
        "step": "Submit for search engine discovery",
        "effort": "Low",
        "owner": "Content Team",
        "notes": "Update sitemaps, submit to search engines if needed"
    }
]

# Platform-specific prompt templates
PLATFORM_PROMPTS = {
    "reddit": """Generate a Reddit-specific social media strategy to address this gap.

FOCUS AREAS FOR REDDIT:
- Identify 3-5 relevant subreddit communities where the topic is discussed
- Recommend discussion thread ideas with high engagement potential
- Suggest optimal posting times based on subreddit activity patterns
- Propose engagement strategies (answering questions, participating in discussions)
- Include content ideas that would resonate with technical/professional communities

GAP CONTEXT:
- Topic: {topic}
- Gap Type: {gap_type}
- Striim visibility: {striim_vis:.1%}
- Root Cause: {diagnosis}

Ground everything in the evidence when it is provided: thread titles should be the actual
evaluated questions (or close paraphrases), and answers should counter the specific claims
competitors currently win on. Name real subreddits where these exact questions get asked.

Return JSON with:
- recommended_action: overall Reddit strategy naming the specific subreddits and the questions to target
- implementation_steps: concrete, executable actions — each names the subreddit, the exact thread title or question to post/answer, and what the post must say (no steps like "engage with the community")
- content_outline: full draft thread titles and the specific talking points/product facts for each, tied to the evaluated questions
- hashtags: relevant subreddit communities and keywords (e.g., r/dataengineering, r/DevOps, #DataIntegration)
- frequency: posting frequency and engagement schedule (e.g., "2-3 times weekly, comments daily")
- evidence_summary: why this Reddit strategy will help close the gap, citing the specific questions and claims from the evidence""",

    "linkedin": """Generate a LinkedIn-specific social media strategy to address this gap.

FOCUS AREAS FOR LINKEDIN:
- Recommend thought leadership content pieces on the topic
- Suggest professional articles, insights, or opinion pieces
- Identify relevant LinkedIn groups and professional communities
- Recommend article sharing strategy and professional tone
- Propose engagement with industry influencers and peers
- Include strategies for establishing Striim as a thought leader

GAP CONTEXT:
- Topic: {topic}
- Gap Type: {gap_type}
- Striim visibility: {striim_vis:.1%}
- Root Cause: {diagnosis}

Ground everything in the evidence when it is provided: post topics should directly answer
the evaluated questions, and thought-leadership angles should counter the specific claims
competitors currently win on in AI answers.

Return JSON with:
- recommended_action: overall LinkedIn strategy naming the specific questions and competitor claims to target
- implementation_steps: concrete, executable actions — each names the exact post/article title, its core argument, and what publishing it looks like (no steps like "establish thought leadership")
- content_outline: full draft post titles with opening hooks and the specific talking points for each, tied to the evaluated questions
- hashtags: relevant LinkedIn groups, hashtags, and keywords (e.g., #DataIntegration, #ETL, #CloudData)
- frequency: posting frequency and engagement schedule (e.g., "2-3 article posts weekly")
- evidence_summary: why this LinkedIn strategy will establish authority and close the gap, citing the specific questions and claims from the evidence""",

    "facebook": """Generate a Facebook-specific social media strategy to address this gap.

FOCUS AREAS FOR FACEBOOK:
- Identify relevant Facebook groups and communities in the professional/technical space
- Recommend recurring series or regular content themes
- Suggest discussion prompts and community engagement strategies
- Include tips for building community loyalty and consistent engagement
- Recommend content formats (educational posts, case studies, polls)
- Propose strategies for leveraging Facebook's algorithmic reach

GAP CONTEXT:
- Topic: {topic}
- Gap Type: {gap_type}
- Striim visibility: {striim_vis:.1%}
- Root Cause: {diagnosis}

Ground everything in the evidence when it is provided: discussion prompts should be the
actual evaluated questions (or close paraphrases), and content should counter the specific
claims competitors currently win on.

Return JSON with:
- recommended_action: overall Facebook community strategy naming the specific groups and questions to target
- implementation_steps: concrete, executable actions — each names the group, the exact post or series installment, and what it must say (no steps like "build community engagement")
- content_outline: named series with the specific installment titles and discussion prompts, tied to the evaluated questions
- hashtags: relevant Facebook groups, hashtags, and keywords (e.g., #DataEngineering, #IntegrationTechnology)
- frequency: posting frequency and engagement schedule (e.g., "2-3 times weekly, moderate discussions daily")
- evidence_summary: why this Facebook strategy will build community and close the gap, citing the specific questions and claims from the evidence"""
}


class RecommendationGenerator:
    """Generate recommendations from detected gaps."""

    def __init__(self, db_conn, engine=None, cost_budget: Optional[float] = None):
        """Initialize with database connection and optional LLM engine.

        Args:
            db_conn: Database connection
            engine: Optional BaseEngine instance for LLM-powered recommendations
            cost_budget: Optional ceiling, in dollars, on LLM spend across
                all gaps in a run. Generation makes up to 5 LLM calls per
                gap, so an unbounded run can cost several dollars. Once the
                budget is used up the remaining gaps fall back to the free
                template recommendations instead of being dropped.
                None means unlimited.
        """
        self.conn = db_conn
        self.engine = engine
        self.cost_budget = cost_budget
        self._recommendation_cost = 0.0
        self._budget_warned = False
        self.methods_context = self._load_methods_context()
        self.rag = MethodsRAG(db_conn, engine)

        # Initialize RAG with methods if available and db_conn is valid
        if self.methods_context and self.conn:
            try:
                self.rag.initialize_methods(self.methods_context)
            except Exception as e:
                logger.warning(f"Failed to initialize RAG: {e}")

    def _estimated_call_cost(self) -> float:
        """Conservative upper bound on the cost of one LLM call.

        Checked *before* calling, so the budget is a real ceiling rather
        than one that is only noticed after it has been blown. Assumes a
        full max_tokens completion, which is what these prompts tend to
        produce.
        """
        if not self.engine:
            return 0.0
        try:
            completion_tokens = int(getattr(self.engine, "max_tokens", 8000))
            return float(
                self.engine.estimate_cost(_EST_PROMPT_TOKENS, completion_tokens)
            )
        except Exception:
            return 0.0

    def _llm_budget_available(self) -> bool:
        """Whether another LLM call still fits inside the run's cost budget."""
        if self.cost_budget is None:
            return True
        # A budget of zero (or less) means the run limit is already spent:
        # no LLM calls at all, whatever they might be estimated to cost.
        if self.cost_budget <= 0:
            if not self._budget_warned:
                logger.warning(
                    "No recommendation LLM budget remaining; "
                    "falling back to template recommendations."
                )
                self._budget_warned = True
            return False
        if self._recommendation_cost + self._estimated_call_cost() <= self.cost_budget:
            return True
        if not self._budget_warned:
            logger.warning(
                f"Recommendation LLM budget reached "
                f"(${self._recommendation_cost:.4f} spent of "
                f"${self.cost_budget:.4f}, next call estimated at "
                f"${self._estimated_call_cost():.4f}); remaining gaps fall "
                f"back to template recommendations."
            )
            self._budget_warned = True
        return False

    def _track_cost(self, call) -> None:
        """Accumulate the cost of one structured LLM call."""
        self._recommendation_cost += getattr(call, "cost", 0.0) or 0.0

    def _load_methods_context(self) -> str:
        """Load AEO methods knowledge base from methods.txt."""
        try:
            with open("methods.txt", "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("methods.txt not found; LLM recommendations will not include methods context")
            return ""

    def _build_gap_evidence(self, gap: Dict) -> str:
        """Assemble the run's concrete evidence for a gap into a prompt block.

        Joins the gap's affected prompts back to the actual question
        text, what the AI engines answered (brands, claims, excerpts),
        and which pages they cited. This is what lets the LLM produce
        recommendations grounded in specifics instead of boilerplate.

        Returns "" when there is no DB connection or nothing to show;
        callers treat an empty block as "generate without evidence".
        """
        if not self.conn:
            return ""
        prompt_ids = list(gap.get("affected_prompts") or [])[:_EVIDENCE_MAX_QUESTIONS]
        if not prompt_ids:
            return ""

        try:
            return self._build_gap_evidence_unsafe(gap, prompt_ids)
        except Exception as e:
            logger.warning(f"Failed to build gap evidence: {e}")
            return ""

    def _build_gap_evidence_unsafe(self, gap: Dict, prompt_ids: list) -> str:
        placeholders = ",".join("?" * len(prompt_ids))
        sections = []

        # 1. The actual questions where Striim underperforms.
        rows = self.conn.execute(
            f"SELECT prompt_text, persona, intent FROM prompts WHERE id IN ({placeholders})",
            prompt_ids,
        ).fetchall()
        if rows:
            lines = []
            for prompt_text, persona, intent in rows:
                qualifiers = ", ".join(q for q in (persona, intent) if q)
                suffix = f" ({qualifiers})" if qualifiers else ""
                lines.append(f'- "{prompt_text}"{suffix}')
            sections.append(
                "ACTUAL QUESTIONS EVALUATED (where Striim underperforms):\n"
                + "\n".join(lines)
            )

        # 2. What the engines answered for those questions, with the
        # extracted brands and claims. Scoped to the gap's run.
        cited_urls: Dict[str, int] = {}
        run_id = gap.get("run_id")
        if run_id:
            answer_rows = self.conn.execute(
                f"""
                SELECT rr.engine, ra.striim_mentioned, ra.brands_found,
                       ra.claims, ra.citations, rr.response_text
                FROM raw_responses rr
                LEFT JOIN response_analysis ra ON ra.raw_response_id = rr.id
                WHERE rr.run_id = ? AND rr.prompt_id IN ({placeholders})
                LIMIT ?
                """,
                [run_id, *prompt_ids, _EVIDENCE_MAX_RESPONSES],
            ).fetchall()

            answer_lines = []
            for engine, striim_mentioned, brands_json, claims_json, citations_json, response_text in answer_rows:
                brands = self._load_json_list(brands_json)
                claims = self._load_json_list(claims_json)
                for url in self._load_json_list(citations_json):
                    if isinstance(url, str):
                        cited_urls[url] = cited_urls.get(url, 0) + 1

                brand_names = ", ".join(
                    b.get("name", "") for b in brands if isinstance(b, dict)
                ) or "none extracted"
                parts = [
                    f"- [{engine}] brands mentioned in order: {brand_names}. "
                    f"Striim mentioned: {'yes' if striim_mentioned else 'no'}."
                ]
                for claim in claims[:_EVIDENCE_MAX_CLAIMS_PER_RESPONSE]:
                    if isinstance(claim, dict) and claim.get("text"):
                        sentiment = claim.get("sentiment", "neutral")
                        parts.append(f'  Claim: "{claim["text"]}" ({sentiment})')
                if response_text:
                    excerpt = response_text[:_EVIDENCE_EXCERPT_CHARS]
                    parts.append(f'  Answer excerpt: "{excerpt}"')
                answer_lines.append("\n".join(parts))

            if answer_lines:
                sections.append(
                    "WHAT THE AI ENGINES ANSWERED:\n" + "\n".join(answer_lines)
                )

        # 3. The specific pages those answers cited, enriched with the
        # citation catalog (title, source category, historical counts),
        # looked up in one query rather than one per URL.
        if cited_urls:
            top_urls = [
                url for url, _count in
                sorted(cited_urls.items(), key=lambda kv: -kv[1])[:_EVIDENCE_MAX_CITED_PAGES]
            ]
            url_placeholders = ",".join("?" * len(top_urls))
            catalog: Dict[str, tuple] = {}
            for cat_url, normalized_url, page_title, source_category, occurrence_count in self.conn.execute(
                f"SELECT url, normalized_url, page_title, source_category, occurrence_count"
                f" FROM citations WHERE url IN ({url_placeholders})"
                f" OR normalized_url IN ({url_placeholders})",
                [*top_urls, *top_urls],
            ):
                for key in (cat_url, normalized_url):
                    if key:
                        catalog.setdefault(key, (page_title, source_category, occurrence_count))

            citation_lines = []
            for url in top_urls:
                detail = ""
                row = catalog.get(url)
                if row:
                    page_title, source_category, occurrence_count = row
                    bits = [b for b in (
                        f'"{page_title}"' if page_title else "",
                        source_category or "",
                        f"cited {occurrence_count}x across runs" if occurrence_count else "",
                    ) if b]
                    if bits:
                        detail = " — " + ", ".join(bits)
                citation_lines.append(f"- {url}{detail}")
            sections.append("PAGES THE AI ENGINES CITED:\n" + "\n".join(citation_lines))

        return "\n\n".join(sections)

    @staticmethod
    def _evidence_block(evidence: str) -> str:
        """Wrap run evidence for inclusion in a prompt ('' when empty)."""
        return f"\nEVIDENCE FROM THIS EVALUATION RUN:\n{evidence}\n" if evidence else ""

    @staticmethod
    def _load_json_list(value) -> list:
        """Parse a JSON column that should hold a list; [] on anything else."""
        if isinstance(value, list):
            return value
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

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

    def _diagnose_gap_with_llm(
        self,
        gap: Dict,
        evidence: Optional[str] = None,
        methods_context: Optional[str] = None,
    ) -> Optional[Dict]:
        """Use LLM to deeply analyze gap and diagnose root causes.

        Args:
            gap: Gap dict from gaps table
            evidence: Prebuilt gap evidence; built from the gap when None.
            methods_context: Prebuilt RAG context; retrieved when None.

        Returns:
            Dict with diagnosis and root_causes, or None if LLM unavailable
        """
        if not self.engine or not self._llm_budget_available():
            return None

        gap_type = gap["gap_type"]
        topic = gap["topic"]
        striim_vis = gap.get("striim_visibility", 0)
        competitor_vis = gap.get("top_competitor_visibility", 0)
        competitor_name = gap.get("top_competitor_name", "top competitor")

        if methods_context is None:
            methods_context = self._get_methods_context_for_gap(gap)
        if evidence is None:
            evidence = self._build_gap_evidence(gap)
        evidence_block = self._evidence_block(evidence)

        prompt = f"""Analyze this AEO visibility gap and diagnose root causes.

GAP DETAILS:
- Type: {gap_type}
- Topic: {topic}
- Striim visibility: {striim_vis:.1%}
- {competitor_name} visibility: {competitor_vis:.1%}
- Evidence sources: {len(gap.get('evidence_ids', []))}
- Affected questions: {len(gap.get('affected_prompts', []))}
{evidence_block}
RELEVANT AEO METHODS:
{methods_context}

Using only 2025-26 AEO best practices, analyze what's causing this gap. What's the likely root cause?
Consider: page organization, content depth, authority signals, technical accessibility, content recency.
Base the diagnosis on the evidence: which specific questions Striim loses, what the winning
answers contain that Striim's content evidently does not, and which competitor pages get cited.

Return JSON with:
- diagnosis: 1-2 sentence summary of the root cause, referencing the specific questions or cited pages that show it
- root_causes: array of specific causes tied to the evidence (e.g., "no Striim page answers the schema-drift questions that fivetran.com/docs/oracle-cdc answers")

Focus on actionable diagnoses that point to specific improvements. Avoid generic causes that could apply to any topic."""

        try:
            call = self.engine.run_with_structured_output(prompt, GAP_DIAGNOSIS_SCHEMA)
            self._track_cost(call)
            return call.data
        except Exception as e:
            logger.warning(f"LLM diagnosis failed: {e}")
            return None

    def _generate_article_recommendation_with_llm(
        self,
        gap: Dict,
        diagnosis: Dict,
        evidence: Optional[str] = None,
        methods_context: Optional[str] = None,
    ) -> Optional[Dict]:
        """Use LLM to generate article suggestion and detailed recommendation.

        Args:
            gap: Gap dict from gaps table
            diagnosis: Dict with diagnosis and root_causes from _diagnose_gap_with_llm
            evidence: Prebuilt gap evidence; built from the gap when None.
            methods_context: Prebuilt RAG context; retrieved when None.

        Returns:
            Dict with full recommendation structure, or None if LLM unavailable
        """
        if not self.engine or not self._llm_budget_available():
            return None

        topic = gap["topic"]
        striim_vis = gap.get("striim_visibility", 0)
        competitor_vis = gap.get("top_competitor_visibility", 0)
        competitor_name = gap.get("top_competitor_name", "top competitor")

        if methods_context is None:
            methods_context = self._get_methods_context_for_gap(gap)
        if evidence is None:
            evidence = self._build_gap_evidence(gap)
        evidence_block = self._evidence_block(evidence)

        prompt = f"""Generate a specific article recommendation with a full content brief to address this AEO gap.

DIAGNOSIS:
{diagnosis.get('diagnosis', '')}

ROOT CAUSES:
{json.dumps(diagnosis.get('root_causes', []), indent=2)}

GAP CONTEXT:
- Topic: {topic}
- Striim visibility: {striim_vis:.1%}
- {competitor_name} visibility: {competitor_vis:.1%}
{evidence_block}
RELEVANT AEO METHODS:
{methods_context}
{_SPECIFICITY_RULES}

Using only 2025-26 AEO practices, recommend ONE specific article Striim should create,
and express its full content brief as the implementation steps, in this order:

1. First step: state the exact working title, the target URL slug (e.g.
   striim.com/blog/<slug> or striim.com/docs/<slug>), and which cited competitor
   page from the evidence this article must displace — and what that page does
   that currently wins the citation.
2. Then ONE step per major H2 section of the article. Each step names the exact
   H2 heading and lists, verbatim, the evaluated question(s) from the evidence
   that the section must answer in its first paragraph. Use notes for the key
   points, data, examples, or product specifics the section needs, and what
   "done" looks like.
3. Then concrete finishing steps: which schema markup to add (FAQPage, HowTo,
   and/or Article — say which and for what content), which existing Striim pages
   should link to the new article, technical review, and publish.
4. Final step: re-run the affected evaluation questions and compare visibility.

Every step needs effort (Low/Medium/High) and owner (Content Team/Product Manager/Engineering).

Return JSON with:
- article_suggestion: {{title, recommended_sections (the exact H2 headings), how_it_improves_aeo (tied to the specific questions and cited pages), source_type}}
- recommended_action: one sentence naming the article title, target URL, and the competitor page it displaces
- evidence_summary: why this will work, citing the specific evidence (questions lost, pages cited)
- implementation_steps: array of {{step, effort, owner, notes}} following the structure above"""

        try:
            call = self.engine.run_with_structured_output(prompt, ARTICLE_RECOMMENDATION_SCHEMA)
            self._track_cost(call)
            return call.data
        except Exception as e:
            logger.warning(f"LLM article recommendation failed: {e}")
            return None

    def _generate_social_media_recommendation_with_llm(
        self,
        gap: Dict,
        platform: str,
        diagnosis: Dict,
        evidence: Optional[str] = None,
    ) -> Optional[Dict]:
        """Use LLM to generate platform-specific social media recommendation.

        Args:
            gap: Gap dict from gaps table
            platform: Platform name ('reddit', 'linkedin', or 'facebook')
            diagnosis: Dict with diagnosis from _diagnose_gap_with_llm
            evidence: Prebuilt gap evidence; built from the gap when None.

        Returns:
            Dict with social media recommendation structure, or None if LLM unavailable
        """
        if (
            not self.engine
            or platform not in PLATFORM_PROMPTS
            or not self._llm_budget_available()
        ):
            return None

        topic = gap["topic"]
        gap_type = gap["gap_type"]
        striim_vis = gap.get("striim_visibility", 0)
        diagnosis_text = diagnosis.get("diagnosis", "visibility gap detected")

        # Use platform-specific prompt template. The evidence block is
        # concatenated rather than passed through .format(): it contains
        # verbatim answer text that may include literal braces.
        prompt_template = PLATFORM_PROMPTS[platform]
        prompt = prompt_template.format(
            topic=topic,
            gap_type=gap_type,
            striim_vis=striim_vis,
            diagnosis=diagnosis_text
        )
        if evidence is None:
            evidence = self._build_gap_evidence(gap)
        if evidence:
            prompt = (
                f"EVIDENCE FROM THIS EVALUATION RUN:\n{evidence}\n"
                f"{_SPECIFICITY_RULES}\n\n{prompt}"
            )

        try:
            call = self.engine.run_with_structured_output(prompt, SOCIAL_MEDIA_RECOMMENDATION_SCHEMA)
            self._track_cost(call)
            return call.data
        except Exception as e:
            logger.warning(f"LLM social media recommendation failed for {platform}: {e}")
            return None

    def _base_recommendation(self, gap: Dict, rec_type: str) -> Dict:
        """Fields shared by every recommendation built for a gap."""
        return {
            "id": str(uuid.uuid4()),
            "gap_id": gap["id"],
            "type": rec_type,
            "affected_pages": [f"https://striim.com/topic/{gap['topic'].lower()}"],
            "confidence": gap["confidence"],
            "created_timestamp": datetime.now().isoformat(),
        }

    def generate_for_gap(self, gap: Dict) -> list[Dict]:
        """
        Generate recommendations for a gap using LLM analysis when available.
        Returns a list containing 1 article recommendation + 3 social media recommendations.

        Args:
            gap: Gap dict from gaps table

        Returns:
            List of recommendation dicts (1 article + up to 3 social media per gap)
        """
        gap_type = gap["gap_type"]
        topic = gap["topic"]

        # Try LLM-based recommendation first. Evidence and RAG context are
        # built once per gap and shared by every LLM call for it (the
        # diagnosis, the article, and each social platform).
        llm_recommendation = None
        diagnosis = None
        evidence = None
        if self.engine and self._llm_budget_available():
            evidence = self._build_gap_evidence(gap)
            methods_context = self._get_methods_context_for_gap(gap)
            diagnosis = self._diagnose_gap_with_llm(
                gap, evidence=evidence, methods_context=methods_context
            )
            if diagnosis:
                llm_recommendation = self._generate_article_recommendation_with_llm(
                    gap, diagnosis, evidence=evidence, methods_context=methods_context
                )

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
        evidence_summary = f"{len(gap.get('evidence_ids', []))} evidence sources"

        # Assemble the article recommendation's content, from the LLM
        # output when available and from templates otherwise.
        article_evidence = evidence_summary
        llm_fields: Dict = {}
        if llm_recommendation and diagnosis:
            problem = (
                f"Striim appears in only {gap['striim_visibility']:.0%} of answers for '{topic}', "
                f"while {gap['top_competitor_name']} appears in {gap['top_competitor_visibility']:.0%}. "
                f"Root cause: {diagnosis.get('diagnosis', '')}"
            )
            recommended_action = llm_recommendation.get("recommended_action", "")
            suggested_owner = "Content Team"
            effort = 2
            article_evidence = llm_recommendation.get("evidence_summary", evidence_summary)
            implementation_steps = llm_recommendation.get(
                "implementation_steps", _FALLBACK_STEPS_VISIBILITY
            )
            llm_fields = {
                "diagnosis": diagnosis.get("diagnosis", ""),
                "root_causes": diagnosis.get("root_causes", []),
                "article_suggestion": llm_recommendation.get("article_suggestion", {}),
            }
        elif gap_type == "visibility":
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
            implementation_steps = _FALLBACK_STEPS_VISIBILITY

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
            implementation_steps = _FALLBACK_STEPS_CITATION

        else:
            problem = f"Gap detected: {gap_type}"
            recommended_action = f"Investigate {gap_type} gap for '{topic}'"
            suggested_owner = "Product Manager"
            effort = 1
            implementation_steps = [
                {
                    "step": f"Investigate {gap_type} gap for '{topic}'",
                    "effort": "Medium",
                    "owner": "Product Manager",
                }
            ]

        recommendations = [{
            **self._base_recommendation(gap, "article"),
            "problem": problem,
            "evidence_summary": article_evidence,
            "recommended_action": recommended_action,
            "suggested_owner": suggested_owner,
            "priority": priority,
            "estimated_effort": effort,
            "measurement_plan": (
                f"Re-run '{topic}' questions after implementation and compare visibility metrics."
            ),
            "will_auto_publish": will_auto_publish,
            "status": status,
            "implementation_steps": implementation_steps,
            **llm_fields,
        }]

        # Social media recommendations accompany only a successful LLM article.
        if llm_recommendation and diagnosis:
            for platform in PLATFORM_PROMPTS:
                social_rec = self._generate_social_media_recommendation_with_llm(
                    gap, platform, diagnosis, evidence=evidence
                )
                if social_rec:
                    recommendations.append({
                        **self._base_recommendation(gap, "social_media"),
                        "platform": platform,
                        "problem": problem,
                        "evidence_summary": social_rec.get("evidence_summary", evidence_summary),
                        "recommended_action": social_rec.get("recommended_action", ""),
                        "suggested_owner": "Marketing Team",
                        # Social media is lower priority and effort than the article.
                        "priority": max(1, priority - 2),
                        "estimated_effort": 1,
                        "measurement_plan": (
                            f"Track engagement metrics on {platform} posts related to '{topic}'."
                        ),
                        "will_auto_publish": False,  # Social media recs don't auto-publish
                        "status": "draft",
                        # LLM-generated social media fields
                        "implementation_steps": social_rec.get("implementation_steps", []),
                        "content_outline": social_rec.get("content_outline", ""),
                        "hashtags": social_rec.get("hashtags", []),
                        "frequency": social_rec.get("frequency", ""),
                    })

        return recommendations

    def generate_for_run(self, run_id: str, use_llm: bool = True) -> tuple[list[Dict], float]:
        """
        Generate recommendations for all gaps in a run.
        Each gap produces multiple recommendations (1 article + up to 3 social media).

        Args:
            run_id: ID of evaluation_runs record
            use_llm: Whether to use LLM for deep gap analysis (default True if engine available)

        Returns:
            Tuple of (Flattened list of all recommendation dicts, total cost in dollars)
        """
        # Reset per-run cost accounting (and the one-shot budget warning).
        self._recommendation_cost = 0.0
        self._budget_warned = False

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
                # Needed by the evidence builder to scope raw_responses
                # and response_analysis queries to this run.
                "run_id": run_id,
            }
            gaps.append(gap_dict)

        recommendations = []
        for gap in gaps:
            # generate_for_gap now returns a list of recommendations (1 article + up to 3 social media)
            gap_recs = self.generate_for_gap(gap)
            recommendations.extend(gap_recs)

        return recommendations, self._recommendation_cost
