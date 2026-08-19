"""Gap detection thresholds and priority scoring."""

from __future__ import annotations

from typing import Literal

# Visibility gap thresholds by topic priority
VISIBILITY_THRESHOLDS = {
    "High": 0.15,      # High-priority topics: Striim < 15%
    "Medium": 0.05,    # Medium: < 5%
    "Low": 0.02,       # Low: < 2%
}

# Competitive multiplier for visibility gaps
COMPETITOR_MULTIPLIER = 2.0  # Gap if competitor > 2x Striim


def should_flag_visibility_gap(
    striim_mention_rate: float,
    top_competitor_mention_rate: float,
    topic_priority: str = "Medium",
) -> bool:
    """
    Determine if a visibility gap exists.

    Args:
        striim_mention_rate: Striim mention rate (0.0-1.0)
        top_competitor_mention_rate: Top competitor mention rate
        topic_priority: Topic priority level (case-insensitive)

    Returns:
        True if gap should be flagged
    """
    normalized_priority = (topic_priority or "Medium").strip().capitalize()
    threshold = VISIBILITY_THRESHOLDS.get(normalized_priority, 0.05)

    # Gap if Striim below threshold OR competitor > 2x Striim
    below_threshold = striim_mention_rate < threshold
    competitive_disadvantage = (
        top_competitor_mention_rate > 0 and
        striim_mention_rate > 0 and
        top_competitor_mention_rate > COMPETITOR_MULTIPLIER * striim_mention_rate
    )

    return below_threshold or competitive_disadvantage


def calculate_gap_priority(
    striim_visibility: float,
    competitor_visibility: float,
) -> Literal["high", "medium", "low"]:
    """
    Calculate gap priority based on visibility metrics.

    Args:
        striim_visibility: Striim mention/visibility rate
        competitor_visibility: Top competitor visibility rate

    Returns:
        Priority level
    """
    gap_ratio = (competitor_visibility - striim_visibility) / max(striim_visibility, 0.01)

    if gap_ratio > 3.0:
        return "high"
    elif gap_ratio > 1.5:
        return "medium"
    else:
        return "low"
