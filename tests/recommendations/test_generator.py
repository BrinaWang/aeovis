"""Tests for recommendation generation."""

import pytest
from unittest.mock import Mock
from aeo_eval.recommendations.generator import RecommendationGenerator
from aeo_eval.recommendations.approval import should_auto_approve, approve_recommendation


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
    rec = gen.generate_for_gap(gap)

    assert "CDC" in rec["problem"]
    assert "Fivetran" in rec["problem"]
    assert rec["priority"] >= 6
    assert rec["status"] == "draft"


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
    }

    # Setup mock to return different responses for diagnosis and recommendation
    mock_engine.run_with_structured_output.side_effect = [diagnosis_response, rec_response]

    gen = RecommendationGenerator(None, engine=mock_engine)
    rec = gen.generate_for_gap(gap)

    # Verify LLM fields are present
    assert "diagnosis" in rec
    assert "root_causes" in rec
    assert "article_suggestion" in rec
    assert rec["article_suggestion"]["title"] == "Complete CDC Implementation Guide for Data Integration"
    assert len(rec["article_suggestion"]["recommended_sections"]) == 5
    assert rec["status"] == "draft"  # Not auto-published since confidence check passes but priority check may not
