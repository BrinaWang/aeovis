"""Tests for recommendation update methods in SQLiteStore."""

import pytest
import json
import uuid
import tempfile
from pathlib import Path
from datetime import datetime
from aeo_eval.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store():
    """Create a SQLiteStore for testing using a temporary file.

    Uses a file-based database instead of in-memory to avoid issues with
    the shared-cache in-memory database being destroyed when connections close.
    """
    # Create a temporary database file
    temp_dir = Path(tempfile.gettempdir())
    db_file = temp_dir / f"test_store_{uuid.uuid4().hex[:8]}.db"

    store = SQLiteStore(str(db_file))
    store.init_db()

    yield store

    # Clean up the temporary database file
    try:
        db_file.unlink(missing_ok=True)
    except Exception:
        pass


def create_test_gap(store, gap_id=None):
    """Helper to create a test gap with its required evaluation run."""
    from aeo_eval.models.result import EvaluationRun

    run_id = str(uuid.uuid4())[:8]
    gap_id = gap_id or str(uuid.uuid4())[:8]

    # Create evaluation run
    run = EvaluationRun(
        run_id=run_id,
        run_timestamp=datetime.now(),
        engine="openai",
        model_version="gpt-4",
        prompts_run=1,
        prompts_succeeded=1,
        prompts_failed=0,
        filters_applied={},
        total_cost=0.01,
        duration_seconds=10,
    )
    store.save_evaluation_run(run)

    # Create gap
    gap_data = {
        "id": gap_id,
        "topic": "data-integration",
        "gap_type": "visibility",
        "striim_visibility": 0.3,
        "top_competitor_visibility": 0.8,
        "top_competitor_name": "Fivetran",
        "affected_prompts": ["prompt-001"],
        "evidence_ids": [run_id],
        "priority": "high",
        "confidence": "high",
        "run_id": run_id,
        "created_timestamp": datetime.now().isoformat(),
    }
    store.save_gap(gap_data)
    return gap_data


def create_test_recommendation(store, gap_id=None, rec_id=None):
    """Helper to create a test recommendation."""
    if gap_id is None:
        gap = create_test_gap(store)
        gap_id = gap["id"]

    rec_id = rec_id or str(uuid.uuid4())[:8]

    rec_data = {
        "id": rec_id,
        "gap_id": gap_id,
        "problem": "Low visibility in Striim documentation",
        "evidence_summary": "Only 30% of queries mention Striim",
        "recommended_action": "Create guide on CDC implementation",
        "affected_pages": ["https://docs.striim.com/cdc"],
        "suggested_owner": "Marketing",
        "priority": 8,
        "estimated_effort": 2,
        "measurement_plan": "Track mention rate over 3 months",
        "confidence": "high",
        "status": "draft",
        "created_timestamp": datetime.now().isoformat(),
    }
    store.save_recommendation(rec_data)
    return rec_data


class TestGetRecommendation:
    """Test get_recommendation method."""

    def test_get_existing_recommendation(self, store):
        """Test fetching an existing recommendation."""
        rec_data = create_test_recommendation(store)
        rec = store.get_recommendation(rec_data["id"])
        assert rec is not None
        assert rec["id"] == rec_data["id"]
        assert rec["problem"] == "Low visibility in Striim documentation"
        assert rec["status"] == "draft"
        assert rec["priority"] == 8

    def test_get_nonexistent_recommendation(self, store):
        """Test fetching a non-existent recommendation returns None."""
        rec = store.get_recommendation("rec-nonexistent")
        assert rec is None

    def test_get_recommendation_parses_json_fields(self, store):
        """Test that JSON fields are properly parsed."""
        rec_data = create_test_recommendation(store)
        rec = store.get_recommendation(rec_data["id"])
        assert isinstance(rec["affected_pages"], list)
        assert len(rec["affected_pages"]) == 1
        assert rec["affected_pages"][0] == "https://docs.striim.com/cdc"


class TestUpdateRecommendation:
    """Test update_recommendation method."""

    def test_update_single_field(self, store):
        """Test updating a single field."""
        rec_data = create_test_recommendation(store)
        success = store.update_recommendation(
            rec_data["id"],
            {"problem": "Updated problem description"}
        )
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["problem"] == "Updated problem description"

    def test_update_multiple_fields(self, store):
        """Test updating multiple fields at once."""
        rec_data = create_test_recommendation(store)
        success = store.update_recommendation(
            rec_data["id"],
            {
                "priority": 9,
                "estimated_effort": 3,
                "recommended_action": "Create advanced CDC guide"
            }
        )
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["priority"] == 9
        assert rec["estimated_effort"] == 3
        assert rec["recommended_action"] == "Create advanced CDC guide"

    def test_update_status_field(self, store):
        """Test updating status to new values."""
        rec_data = create_test_recommendation(store)
        success = store.update_recommendation(
            rec_data["id"],
            {"status": "pending_publish"}
        )
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["status"] == "pending_publish"

    def test_update_status_to_edited(self, store):
        """Test updating status to 'edited'."""
        rec_data = create_test_recommendation(store)
        success = store.update_recommendation(
            rec_data["id"],
            {"status": "edited"}
        )
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["status"] == "edited"

    def test_update_nonexistent_recommendation_returns_false(self, store):
        """Test updating non-existent recommendation returns False."""
        success = store.update_recommendation(
            "rec-nonexistent",
            {"problem": "New problem"}
        )
        assert success is False

    def test_update_empty_updates_returns_false(self, store):
        """Test that empty updates dict returns False."""
        rec_data = create_test_recommendation(store)
        success = store.update_recommendation(rec_data["id"], {})
        assert success is False

    def test_update_ignores_invalid_fields(self, store):
        """Test that invalid fields are ignored."""
        rec_data = create_test_recommendation(store)
        success = store.update_recommendation(
            rec_data["id"],
            {
                "problem": "New problem",
                "invalid_field": "should be ignored",
                "another_invalid": "also ignored"
            }
        )
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["problem"] == "New problem"

    def test_update_with_json_field(self, store):
        """Test updating fields that contain JSON."""
        rec_data = create_test_recommendation(store)
        new_pages = ["https://docs.striim.com/cdc", "https://docs.striim.com/enrichment"]
        success = store.update_recommendation(
            rec_data["id"],
            {"affected_pages": json.dumps(new_pages)}
        )
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert isinstance(rec["affected_pages"], list)
        assert len(rec["affected_pages"]) == 2


class TestApproveRecommendation:
    """Test approve_recommendation method."""

    def test_approve_recommendation(self, store):
        """Test approving a recommendation."""
        rec_data = create_test_recommendation(store)
        success = store.approve_recommendation(rec_data["id"], "alice@example.com")
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["status"] == "approved"
        assert rec["approved_by"] == "alice@example.com"
        assert rec["approval_timestamp"] is not None

    def test_approve_nonexistent_recommendation(self, store):
        """Test approving non-existent recommendation returns False."""
        success = store.approve_recommendation("rec-nonexistent", "alice@example.com")
        assert success is False

    def test_approve_sets_timestamp(self, store):
        """Test that approval sets a valid timestamp."""
        rec_data = create_test_recommendation(store)
        before = datetime.now()
        store.approve_recommendation(rec_data["id"], "alice@example.com")
        rec = store.get_recommendation(rec_data["id"])
        timestamp = datetime.fromisoformat(rec["approval_timestamp"])
        assert timestamp >= before

    def test_approve_preserves_other_fields(self, store):
        """Test that approval doesn't modify other fields."""
        rec_data = create_test_recommendation(store)
        original_problem = rec_data["problem"]
        store.approve_recommendation(rec_data["id"], "alice@example.com")
        rec = store.get_recommendation(rec_data["id"])
        assert rec["problem"] == original_problem
        assert rec["priority"] == 8


class TestRejectRecommendation:
    """Test reject_recommendation method."""

    def test_reject_recommendation(self, store):
        """Test rejecting a recommendation."""
        rec_data = create_test_recommendation(store)
        success = store.reject_recommendation(rec_data["id"], "Insufficient evidence")
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["status"] == "rejected"
        assert rec["review_notes"] is not None

    def test_reject_nonexistent_recommendation(self, store):
        """Test rejecting non-existent recommendation returns False."""
        success = store.reject_recommendation("rec-nonexistent", "Some reason")
        assert success is False

    def test_reject_stores_review_notes(self, store):
        """Test that review notes are stored."""
        rec_data = create_test_recommendation(store)
        reason = "Not aligned with Q3 roadmap"
        store.reject_recommendation(rec_data["id"], reason)
        rec = store.get_recommendation(rec_data["id"])
        # Review notes should be stored as JSON
        if isinstance(rec["review_notes"], str):
            notes = json.loads(rec["review_notes"])
            assert notes["reason"] == reason
        else:
            assert rec["review_notes"]["reason"] == reason

    def test_reject_with_empty_notes(self, store):
        """Test rejecting with empty notes."""
        rec_data = create_test_recommendation(store)
        success = store.reject_recommendation(rec_data["id"], "")
        assert success is True
        rec = store.get_recommendation(rec_data["id"])
        assert rec["status"] == "rejected"

    def test_reject_preserves_other_fields(self, store):
        """Test that rejection doesn't modify other fields."""
        rec_data = create_test_recommendation(store)
        original_problem = rec_data["problem"]
        store.reject_recommendation(rec_data["id"], "Some reason")
        rec = store.get_recommendation(rec_data["id"])
        assert rec["problem"] == original_problem
        assert rec["priority"] == 8


class TestWorkflow:
    """Test complete recommendation workflow."""

    def test_draft_to_approved_workflow(self, store):
        """Test complete workflow from draft to approved."""
        rec_data = create_test_recommendation(store)
        rec_id = rec_data["id"]

        # Start as draft
        rec = store.get_recommendation(rec_id)
        assert rec["status"] == "draft"

        # Update and change to pending_publish
        store.update_recommendation(rec_id, {"status": "pending_publish"})
        rec = store.get_recommendation(rec_id)
        assert rec["status"] == "pending_publish"

        # Approve
        store.approve_recommendation(rec_id, "reviewer@example.com")
        rec = store.get_recommendation(rec_id)
        assert rec["status"] == "approved"
        assert rec["approved_by"] == "reviewer@example.com"

    def test_draft_to_edited_to_approved_workflow(self, store):
        """Test workflow with editing before approval."""
        rec_data = create_test_recommendation(store)
        rec_id = rec_data["id"]

        # Update fields
        store.update_recommendation(
            rec_id,
            {
                "problem": "Revised problem",
                "status": "edited"
            }
        )
        rec = store.get_recommendation(rec_id)
        assert rec["status"] == "edited"
        assert rec["problem"] == "Revised problem"

        # Approve
        store.approve_recommendation(rec_id, "alice@example.com")
        rec = store.get_recommendation(rec_id)
        assert rec["status"] == "approved"

    def test_draft_to_rejected_workflow(self, store):
        """Test workflow that ends in rejection."""
        rec_data = create_test_recommendation(store)
        rec_id = rec_data["id"]

        store.reject_recommendation(rec_id, "Priority too low for Q3")
        rec = store.get_recommendation(rec_id)
        assert rec["status"] == "rejected"

    def test_multiple_recommendation_updates(self, store):
        """Test managing multiple recommendations."""
        gap = create_test_gap(store)
        gap_id = gap["id"]

        # Create multiple recommendations
        rec_ids = []
        for i in range(3):
            rec_data = create_test_recommendation(store, gap_id=gap_id, rec_id=f"rec-multi-{i}")
            rec_ids.append(rec_data["id"])

        # Update each with different workflows
        store.update_recommendation(rec_ids[0], {"status": "pending_publish"})
        store.approve_recommendation(rec_ids[1], "alice@example.com")
        store.reject_recommendation(rec_ids[2], "Not ready")

        # Verify states
        rec0 = store.get_recommendation(rec_ids[0])
        rec1 = store.get_recommendation(rec_ids[1])
        rec2 = store.get_recommendation(rec_ids[2])

        assert rec0["status"] == "pending_publish"
        assert rec1["status"] == "approved"
        assert rec2["status"] == "rejected"
