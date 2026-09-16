"""Tests for recommendation generation."""

import json
import sqlite3
from pathlib import Path

import pytest
from unittest.mock import Mock
from aeo_eval.recommendations.generator import RecommendationGenerator
from aeo_eval.recommendations.approval import should_auto_approve, approve_recommendation

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "aeo_eval" / "storage" / "sqlite_schema.sql"


def test_generate_visibility_recommendation():
    """Test recommendation generation for visibility gap."""
    gap = {
        "id": "gap1",
        "gap_type": "visibility",
        "topic": "CDC",
        "striim_visibility": 0.10,
        "top_competitor_visibility": 0.50,
        "top_competitor_name": "Fivetran",
        "priority": "high",
        "confidence": "high",
        "evidence_ids": ["e1", "e2"],
    }

    gen = RecommendationGenerator(None)  # Don't need DB for single gap
    recs = gen.generate_for_gap(gap)

    # Should return a list with at least the article recommendation
    assert isinstance(recs, list)
    assert len(recs) > 0

    # Find the article recommendation
    article_rec = next((r for r in recs if r.get("type") == "article"), None)
    assert article_rec is not None

    assert "CDC" in article_rec["problem"]
    assert "Fivetran" in article_rec["problem"]
    assert article_rec["priority"] >= 6
    assert article_rec["status"] == "draft"
    assert "implementation_steps" in article_rec
    assert len(article_rec["implementation_steps"]) > 0
    assert all("step" in step and "effort" in step and "owner" in step for step in article_rec["implementation_steps"])


def test_generate_citation_recommendation():
    """Test recommendation generation for citation gap with fallback implementation steps."""
    gap = {
        "id": "gap2",
        "gap_type": "citation",
        "topic": "Schema Evolution",
        "striim_visibility": 0.25,
        "top_competitor_visibility": 0.60,
        "top_competitor_name": "Talend",
        "priority": "medium",
        "confidence": "medium",
        "evidence_ids": ["e1", "e2", "e3"],
    }

    gen = RecommendationGenerator(None)
    recs = gen.generate_for_gap(gap)

    # Should return a list with at least the article recommendation
    assert isinstance(recs, list)
    assert len(recs) > 0

    # Find the article recommendation
    article_rec = next((r for r in recs if r.get("type") == "article"), None)
    assert article_rec is not None

    assert "Schema Evolution" in article_rec["problem"]
    assert article_rec["priority"] == 5
    assert "implementation_steps" in article_rec
    assert len(article_rec["implementation_steps"]) > 0
    # Verify citation gap has appropriate implementation steps
    assert any("citation" in step.get("notes", "").lower() or "content" in step.get("step", "").lower() or "Identify" in step.get("step", "")
               for step in article_rec["implementation_steps"])


def test_should_auto_approve():
    """Test auto-approval logic."""
    high_priority_high_confidence = {
        "priority": 8,
        "confidence": "high",
    }
    assert should_auto_approve(high_priority_high_confidence) is True

    medium_priority = {
        "priority": 5,
        "confidence": "high",
    }
    assert should_auto_approve(medium_priority) is False


def test_approve_recommendation():
    """Test recommendation approval."""
    rec = {
        "id": "rec1",
        "status": "draft",
    }

    approved = approve_recommendation(rec, "user@striim.com")

    assert approved["status"] == "approved"
    assert approved["approved_by"] == "user@striim.com"
    assert "approval_timestamp" in approved


def test_generate_llm_recommendation():
    """Test LLM-based recommendation generation."""
    gap = {
        "id": "gap1",
        "gap_type": "visibility",
        "topic": "CDC",
        "striim_visibility": 0.10,
        "top_competitor_visibility": 0.50,
        "top_competitor_name": "Fivetran",
        "priority": "high",
        "confidence": "high",
        "evidence_ids": ["e1", "e2"],
        "affected_prompts": ["p1", "p2"],
    }

    # Mock engine with structured output
    mock_engine = Mock()
    mock_engine.run_with_structured_output = Mock()

    # Mock diagnosis response
    diagnosis_response = Mock()
    diagnosis_response.data = {
        "diagnosis": "Missing comprehensive CDC implementation guide",
        "root_causes": ["incomplete content", "poor page organization"],
    }
    diagnosis_response.cost = 0.0

    # Mock recommendation response
    rec_response = Mock()
    rec_response.data = {
        "diagnosis": "Missing comprehensive CDC implementation guide",
        "root_causes": ["incomplete content", "poor page organization"],
        "article_suggestion": {
            "title": "Complete CDC Implementation Guide for Data Integration",
            "recommended_sections": [
                "Architecture Overview",
                "Initial Load Strategy",
                "Continuous Change Data Capture",
                "Schema Evolution Handling",
                "Performance Optimization",
            ],
            "how_it_improves_aeo": "Comprehensive guide will match AI search intent better than fragmented documentation",
            "source_type": "guide",
        },
        "recommended_action": "Create a comprehensive CDC implementation guide",
        "evidence_summary": "2 evidence sources show gap in visibility",
        "implementation_steps": [
            {
                "step": "Research CDC best practices and competitor content",
                "effort": "Medium",
                "owner": "Content Team",
                "notes": "Review industry standards and current implementations"
            },
            {
                "step": "Write comprehensive guide draft",
                "effort": "High",
                "owner": "Content Team",
                "notes": "Include architecture, patterns, and troubleshooting"
            },
            {
                "step": "Technical review and validation",
                "effort": "Medium",
                "owner": "Product Manager",
                "notes": "Ensure accuracy with current product capabilities"
            },
            {
                "step": "Publish and optimize for discovery",
                "effort": "Low",
                "owner": "Content Team",
                "notes": "Add SEO metadata and internal links"
            }
        ],
    }
    rec_response.cost = 0.0

    # Setup mock to return different responses for diagnosis and recommendation
    # Need to handle social media recommendation calls as well
    mock_engine.run_with_structured_output.side_effect = [
        diagnosis_response,  # First call for article recommendation
        rec_response,  # Second call for article content
        None,  # Social media calls will return None (fail gracefully)
    ]

    gen = RecommendationGenerator(None, engine=mock_engine)
    recs = gen.generate_for_gap(gap)

    # Should return a list with the article recommendation
    assert isinstance(recs, list)
    assert len(recs) > 0

    # Find and verify the article recommendation
    article_rec = next((r for r in recs if r.get("type") == "article"), None)
    assert article_rec is not None
    assert "diagnosis" in article_rec
    assert "root_causes" in article_rec
    assert "article_suggestion" in article_rec
    assert article_rec["article_suggestion"]["title"] == "Complete CDC Implementation Guide for Data Integration"
    assert len(article_rec["article_suggestion"]["recommended_sections"]) == 5
    assert "implementation_steps" in article_rec
    assert len(article_rec["implementation_steps"]) == 4
    assert article_rec["implementation_steps"][0]["effort"] in ["Low", "Medium", "High"]
    assert article_rec["implementation_steps"][0]["owner"] in ["Content Team", "Product Manager", "Engineering"]
    assert article_rec["status"] == "draft"  # Not auto-published since confidence check passes but priority check may not


def _make_seeded_conn():
    """In-memory DB with the real schema and one run's worth of evidence."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_PATH.read_text())

    conn.execute(
        "INSERT INTO evaluation_runs (run_id, timestamp, engine, model, num_prompts, cost)"
        " VALUES ('run-1', '2026-09-15T09:00:00', 'openai', 'gpt-4o', 2, 0.5)"
    )
    conn.execute(
        "INSERT INTO prompts (id, prompt_text, topic, persona, intent) VALUES"
        " ('p1', 'How do I set up Oracle CDC replication to Snowflake?',"
        "  'Oracle CDC', 'data engineer', 'implementation')"
    )
    conn.execute(
        "INSERT INTO prompts (id, prompt_text, topic, persona, intent) VALUES"
        " ('p2', 'What tools support real-time change data capture from Oracle?',"
        "  'Oracle CDC', 'architect', 'evaluation')"
    )
    conn.execute(
        "INSERT INTO raw_responses (id, run_id, prompt_id, engine, response_text, status)"
        " VALUES ('r1', 'run-1', 'p1', 'openai',"
        " 'For Oracle CDC to Snowflake, Fivetran is the most common managed option...',"
        " 'success')"
    )
    conn.execute(
        "INSERT INTO response_analysis"
        " (id, raw_response_id, striim_mentioned, striim_recommended, brands_found, claims, citations)"
        " VALUES ('a1', 'r1', 0, 0, ?, ?, ?)",
        (
            json.dumps([{"name": "Fivetran", "position": 1, "is_recommended": True}]),
            json.dumps([{"text": "Fivetran offers automated schema drift handling",
                         "sentiment": "positive"}]),
            json.dumps(["https://fivetran.com/docs/oracle-cdc"]),
        ),
    )
    conn.execute(
        "INSERT INTO citations (id, url, normalized_url, domain, page_title,"
        " source_category, first_observed, last_observed, occurrence_count)"
        " VALUES ('c1', 'https://fivetran.com/docs/oracle-cdc',"
        " 'fivetran.com/docs/oracle-cdc', 'fivetran.com',"
        " 'Oracle CDC Setup Guide | Fivetran', 'competitor',"
        " '2026-09-01', '2026-09-15', 12)"
    )
    conn.commit()
    return conn


def _evidence_gap(**overrides):
    gap = {
        "id": "gap1",
        "gap_type": "visibility",
        "topic": "Oracle CDC",
        "striim_visibility": 0.10,
        "top_competitor_visibility": 0.50,
        "top_competitor_name": "Fivetran",
        "priority": "high",
        "confidence": "high",
        "evidence_ids": ["e1"],
        "affected_prompts": ["p1", "p2"],
        "run_id": "run-1",
    }
    gap.update(overrides)
    return gap


class _CapturingEngine:
    """Engine that records every prompt and replies with valid data."""

    name = "capturing"
    model_name = "capturing-v1"

    _DIAGNOSIS = {"diagnosis": "Content gap", "root_causes": ["missing guide"]}
    _ARTICLE = {
        "article_suggestion": {
            "title": "T", "recommended_sections": ["S"],
            "how_it_improves_aeo": "H", "source_type": "guide",
        },
        "recommended_action": "A",
        "evidence_summary": "E",
        "implementation_steps": [
            {"step": "S1", "effort": "Low", "owner": "Content Team"}
        ],
    }
    _SOCIAL = {
        "recommended_action": "A", "implementation_steps": ["S1"],
        "content_outline": "O", "hashtags": ["#x"], "frequency": "weekly",
        "evidence_summary": "E",
    }

    def __init__(self):
        self.prompts = []

    def run_with_structured_output(self, prompt_text, schema):
        self.prompts.append(prompt_text)
        props = schema.get("properties", {})
        if "article_suggestion" in props:
            data = self._ARTICLE
        elif "content_outline" in props:
            data = self._SOCIAL
        else:
            data = self._DIAGNOSIS
        return Mock(data=data, cost=0.0)


class TestGapEvidence:
    """Recommendation prompts must be grounded in the run's real evidence.

    Prompts that only carry a topic name and two percentages can only
    produce generic advice; the evidence builder joins the gap back to
    the actual questions, answers, claims, and cited pages.
    """

    def test_evidence_includes_actual_question_text(self):
        gen = RecommendationGenerator(_make_seeded_conn())
        evidence = gen._build_gap_evidence(_evidence_gap())
        assert "How do I set up Oracle CDC replication to Snowflake?" in evidence
        assert "What tools support real-time change data capture from Oracle?" in evidence

    def test_evidence_includes_extracted_claims_about_competitors(self):
        gen = RecommendationGenerator(_make_seeded_conn())
        evidence = gen._build_gap_evidence(_evidence_gap())
        assert "Fivetran offers automated schema drift handling" in evidence

    def test_evidence_includes_cited_competitor_pages(self):
        gen = RecommendationGenerator(_make_seeded_conn())
        evidence = gen._build_gap_evidence(_evidence_gap())
        assert "https://fivetran.com/docs/oracle-cdc" in evidence
        assert "Oracle CDC Setup Guide | Fivetran" in evidence

    def test_evidence_caps_number_of_questions(self):
        conn = _make_seeded_conn()
        extra_ids = []
        for i in range(20):
            pid = f"bulk-{i}"
            extra_ids.append(pid)
            conn.execute(
                "INSERT INTO prompts (id, prompt_text, topic) VALUES (?, ?, 'Oracle CDC')",
                (pid, f"Bulk question number {i} about replication latency?"),
            )
        conn.commit()

        gen = RecommendationGenerator(conn)
        evidence = gen._build_gap_evidence(_evidence_gap(affected_prompts=extra_ids))
        included = sum(
            1 for i in range(20)
            if f"Bulk question number {i} about replication latency?" in evidence
        )
        assert 0 < included <= 8

    def test_evidence_truncates_long_response_excerpts(self):
        conn = _make_seeded_conn()
        conn.execute(
            "UPDATE raw_responses SET response_text = ? WHERE id = 'r1'",
            ("x" * 5000,),
        )
        conn.commit()

        gen = RecommendationGenerator(conn)
        evidence = gen._build_gap_evidence(_evidence_gap())
        assert "x" * 600 not in evidence

    def test_evidence_empty_without_db_connection(self):
        gen = RecommendationGenerator(None)
        assert gen._build_gap_evidence(_evidence_gap()) == ""

    def test_evidence_empty_when_gap_has_no_affected_prompts(self):
        gen = RecommendationGenerator(_make_seeded_conn())
        assert gen._build_gap_evidence(_evidence_gap(affected_prompts=[])) == ""

    def test_evidence_survives_unknown_prompt_ids(self):
        gen = RecommendationGenerator(_make_seeded_conn())
        evidence = gen._build_gap_evidence(
            _evidence_gap(affected_prompts=["nope-1", "nope-2"])
        )
        assert isinstance(evidence, str)

    def test_diagnosis_prompt_contains_evidence(self):
        engine = _CapturingEngine()
        gen = RecommendationGenerator(_make_seeded_conn(), engine=engine)
        gen._diagnose_gap_with_llm(_evidence_gap())
        prompt = engine.prompts[0]
        assert "How do I set up Oracle CDC replication to Snowflake?" in prompt
        assert "https://fivetran.com/docs/oracle-cdc" in prompt

    def test_article_prompt_contains_evidence(self):
        engine = _CapturingEngine()
        gen = RecommendationGenerator(_make_seeded_conn(), engine=engine)
        diagnosis = {"diagnosis": "d", "root_causes": ["r"]}
        gen._generate_article_recommendation_with_llm(_evidence_gap(), diagnosis)
        prompt = engine.prompts[-1]
        assert "How do I set up Oracle CDC replication to Snowflake?" in prompt
        assert "https://fivetran.com/docs/oracle-cdc" in prompt

    def test_social_prompt_contains_evidence(self):
        engine = _CapturingEngine()
        gen = RecommendationGenerator(_make_seeded_conn(), engine=engine)
        diagnosis = {"diagnosis": "d", "root_causes": ["r"]}
        gen._generate_social_media_recommendation_with_llm(
            _evidence_gap(), "reddit", diagnosis
        )
        prompt = engine.prompts[-1]
        assert "How do I set up Oracle CDC replication to Snowflake?" in prompt

    def test_generate_for_run_feeds_evidence_into_prompts(self):
        """End to end: gaps loaded from the DB must carry run_id so the
        evidence builder can scope its queries."""
        conn = _make_seeded_conn()
        conn.execute(
            "INSERT INTO gaps (id, topic, gap_type, striim_visibility,"
            " top_competitor_visibility, top_competitor_name, affected_prompts,"
            " evidence_ids, priority, confidence, run_id, created_timestamp)"
            " VALUES ('gap1', 'Oracle CDC', 'visibility', 0.1, 0.5, 'Fivetran',"
            " ?, ?, 'high', 'high', 'run-1', '2026-09-15T09:00:00')",
            (json.dumps(["p1", "p2"]), json.dumps(["e1"])),
        )
        conn.commit()

        engine = _CapturingEngine()
        gen = RecommendationGenerator(conn, engine=engine)
        recs, _cost = gen.generate_for_run("run-1")

        assert recs, "expected recommendations to be generated"
        assert any(
            "How do I set up Oracle CDC replication to Snowflake?" in p
            for p in engine.prompts
        )


class TestStructuredOutputSchemas:
    """Structured-output schemas must satisfy the API's object rules.

    Every object node needs an explicit "additionalProperties": false,
    otherwise the request fails with a 400 and the whole LLM path
    silently degrades to template-only recommendations.
    """

    @staticmethod
    def _objects_missing_additional_properties(node, path="$"):
        missing = []
        if isinstance(node, dict):
            if node.get("type") == "object" and "additionalProperties" not in node:
                missing.append(path)
            for key, value in node.items():
                missing += TestStructuredOutputSchemas._objects_missing_additional_properties(
                    value, f"{path}.{key}"
                )
        elif isinstance(node, list):
            for i, value in enumerate(node):
                missing += TestStructuredOutputSchemas._objects_missing_additional_properties(
                    value, f"{path}[{i}]"
                )
        return missing

    @pytest.mark.parametrize(
        "schema_name",
        [
            "GAP_DIAGNOSIS_SCHEMA",
            "ARTICLE_RECOMMENDATION_SCHEMA",
            "SOCIAL_MEDIA_RECOMMENDATION_SCHEMA",
        ],
    )
    def test_schema_sets_additional_properties_false(self, schema_name):
        from aeo_eval.recommendations import generator

        schema = getattr(generator, schema_name)
        missing = self._objects_missing_additional_properties(schema, schema_name)
        assert missing == [], f"object nodes missing additionalProperties: {missing}"

    def test_diagnosis_uses_the_shared_schema_constant(self):
        """The diagnosis call must not inline an ad-hoc schema."""
        import inspect
        from aeo_eval.recommendations.generator import RecommendationGenerator

        source = inspect.getsource(RecommendationGenerator._diagnose_gap_with_llm)
        assert "GAP_DIAGNOSIS_SCHEMA" in source


class TestRecommendationCostBudget:
    """LLM spend during recommendation generation must respect a ceiling.

    Generation makes up to 5 LLM calls per gap, so an unbounded run can
    outspend the evaluation itself. Once the budget is used up the
    remaining gaps fall back to free template recommendations rather
    than being dropped.
    """

    class _CountingEngine:
        """Engine whose every structured call costs a fixed amount."""

        name = "counting"
        model_name = "counting-v1"

        def __init__(self, cost_per_call=0.25):
            self.cost_per_call = cost_per_call
            self.calls = 0

        def run_with_structured_output(self, prompt_text, schema):
            self.calls += 1
            return Mock(data={"diagnosis": "d", "root_causes": ["r"]},
                        cost=self.cost_per_call)

    def _generator(self, budget, cost_per_call=0.25):
        engine = self._CountingEngine(cost_per_call)
        gen = RecommendationGenerator(None, engine=engine, cost_budget=budget)
        return gen, engine

    def test_budget_none_allows_unlimited_calls(self):
        gen, engine = self._generator(budget=None)
        for _ in range(10):
            assert gen._llm_budget_available() is True
            gen._track_cost(Mock(cost=1.0))
        assert gen._llm_budget_available() is True

    def test_budget_blocks_calls_once_exhausted(self):
        gen, engine = self._generator(budget=1.0)
        assert gen._llm_budget_available() is True
        gen._track_cost(Mock(cost=0.60))
        assert gen._llm_budget_available() is True
        gen._track_cost(Mock(cost=0.50))  # now 1.10 > 1.00
        assert gen._llm_budget_available() is False

    def test_zero_budget_blocks_every_llm_call(self):
        gen, engine = self._generator(budget=0.0)
        assert gen._llm_budget_available() is False
        assert gen._diagnose_gap_with_llm({"gap_type": "visibility", "topic": "T"}) is None
        assert engine.calls == 0

    def test_diagnose_stops_calling_engine_after_budget_spent(self):
        gen, engine = self._generator(budget=0.30, cost_per_call=0.25)
        gap = {
            "gap_type": "visibility", "topic": "T", "striim_visibility": 0.2,
            "top_competitor_visibility": 0.9, "top_competitor_name": "Rival",
        }
        assert gen._diagnose_gap_with_llm(gap) is not None
        assert engine.calls == 1
        # 0.25 spent of a 0.30 budget still leaves room for one more...
        assert gen._diagnose_gap_with_llm(gap) is not None
        assert engine.calls == 2
        # ...but 0.50 > 0.30 closes the gate.
        assert gen._diagnose_gap_with_llm(gap) is None
        assert engine.calls == 2

    def test_track_cost_tolerates_missing_cost_attribute(self):
        gen, _ = self._generator(budget=1.0)
        gen._track_cost(object())
        gen._track_cost(Mock(cost=None))
        assert gen._recommendation_cost == 0.0


class TestBudgetIsCheckedBeforeSpending:
    """The budget must be a ceiling, not a post-mortem.

    Checking only after a call returned let one full-priced call through
    against a near-zero budget (observed: $0.0196 spent against $0.001).
    """

    class _PricedEngine:
        name = "priced"
        model_name = "priced-v1"
        max_tokens = 8000

        def __init__(self):
            self.calls = 0

        def estimate_cost(self, prompt_tokens, completion_tokens):
            return 0.003 * prompt_tokens / 1000 + 0.015 * completion_tokens / 1000

        def run_with_structured_output(self, prompt_text, schema):
            self.calls += 1
            return Mock(data={"diagnosis": "d", "root_causes": []}, cost=0.12)

    def test_no_call_is_made_when_one_would_not_fit(self):
        engine = self._PricedEngine()
        # One call is estimated at 4k prompt + 8k completion = $0.132.
        gen = RecommendationGenerator(None, engine=engine, cost_budget=0.05)
        assert gen._llm_budget_available() is False
        gap = {
            "gap_type": "visibility", "topic": "T", "striim_visibility": 0.2,
            "top_competitor_visibility": 0.9, "top_competitor_name": "Rival",
        }
        assert gen._diagnose_gap_with_llm(gap) is None
        assert engine.calls == 0, "made an LLM call that the budget could not cover"

    def test_calls_proceed_while_the_estimate_still_fits(self):
        engine = self._PricedEngine()
        gen = RecommendationGenerator(None, engine=engine, cost_budget=0.30)
        gap = {
            "gap_type": "visibility", "topic": "T", "striim_visibility": 0.2,
            "top_competitor_visibility": 0.9, "top_competitor_name": "Rival",
        }
        assert gen._diagnose_gap_with_llm(gap) is not None
        assert gen._diagnose_gap_with_llm(gap) is not None
        # 0.24 spent, next estimate 0.132 -> 0.372 > 0.30, so stop.
        assert gen._diagnose_gap_with_llm(gap) is None
        assert engine.calls == 2

    def test_estimate_is_zero_for_engines_without_pricing(self):
        """A free (mock) engine must not be blocked by a positive budget."""
        engine = Mock(spec=["run_with_structured_output"])
        gen = RecommendationGenerator(None, engine=engine, cost_budget=1.0)
        assert gen._estimated_call_cost() == 0.0
        assert gen._llm_budget_available() is True

    def test_zero_budget_blocks_even_a_free_engine(self):
        """Zero budget means the run limit is spent — stop calling out."""
        engine = Mock(spec=["run_with_structured_output"])
        gen = RecommendationGenerator(None, engine=engine, cost_budget=0.0)
        assert gen._llm_budget_available() is False
