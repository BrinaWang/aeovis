"""Tests for recommendation generation."""

import pytest
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
