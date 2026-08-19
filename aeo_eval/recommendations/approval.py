"""Recommendation approval workflow."""

from __future__ import annotations

from typing import Literal, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def should_auto_approve(recommendation: dict) -> bool:
    """
    Determine if a recommendation should auto-publish.

    Auto-publish rules (from spec):
    - High priority AND high confidence

    Args:
        recommendation: Recommendation dict

    Returns:
        True if should auto-approve
    """
    is_high_priority = recommendation.get("priority", 0) >= 7
    is_high_confidence = recommendation.get("confidence") == "high"

    return is_high_priority and is_high_confidence


def move_to_approval(recommendation: dict) -> None:
    """Move recommendation to pending_approval status."""
    recommendation["status"] = "pending_approval"


def approve_recommendation(
    recommendation: dict,
    approved_by: str,
    review_notes: Optional[str] = None,
) -> dict:
    """
    Approve a recommendation.

    Args:
        recommendation: Recommendation dict
        approved_by: User/role approving
        review_notes: Optional notes on review

    Returns:
        Updated recommendation
    """
    recommendation["status"] = "approved"
    recommendation["approved_by"] = approved_by
    recommendation["approval_timestamp"] = datetime.now().isoformat()
    if review_notes:
        recommendation["review_notes"] = review_notes

    return recommendation


def reject_recommendation(
    recommendation: dict,
    rejected_by: str,
    reason: str,
) -> dict:
    """
    Reject a recommendation.

    Args:
        recommendation: Recommendation dict
        rejected_by: User/role rejecting
        reason: Reason for rejection

    Returns:
        Updated recommendation
    """
    recommendation["status"] = "rejected"
    recommendation["approved_by"] = rejected_by  # Track who rejected
    recommendation["review_notes"] = reason

    return recommendation
