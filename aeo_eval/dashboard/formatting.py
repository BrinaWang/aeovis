"""Display formatting helpers for the dashboard."""

from __future__ import annotations

import re
from typing import Dict, List

EFFORT_LABELS = {1: "Low", 2: "Medium", 3: "High"}
_EFFORT_LEVELS = {label.lower(): level for level, label in EFFORT_LABELS.items()}
_EFFORT_COLORS = {1: "#10b981", 2: "#f59e0b", 3: "#ef4444"}  # green / amber / red

_PLATFORM_COLORS = {
    "article": "#0369a1",   # Blue
    "reddit": "#f97316",    # Orange
    "linkedin": "#0a66c2",  # LinkedIn Blue
    "facebook": "#1877f2",  # Facebook Blue
}


def get_effort_color(effort) -> str:
    """Color for an effort level, given as the 1-3 code or its text label."""
    if isinstance(effort, str):
        effort = _EFFORT_LEVELS.get(effort.lower(), 0)
    return _EFFORT_COLORS.get(effort, "#64748b")


def get_effort_label(effort) -> str:
    """Human label for an effort level, given as the 1-3 code or its text label."""
    if isinstance(effort, int):
        return EFFORT_LABELS.get(effort, str(effort))
    return str(effort).title()


def get_platform_badge(platform) -> str:
    """HTML badge for a recommendation platform ('' when platform is unset)."""
    if not platform:
        return ""
    color = _PLATFORM_COLORS.get(platform.lower(), "#64748b")
    return (
        "<span style='display: inline-block; background-color: "
        f"{color}; color: white; padding: 0.25rem 0.75rem; border-radius: 6px; "
        f"font-size: 0.85rem; font-weight: 500;'>{platform.title()}</span>"
    )


# Break after ./!/? only when the next sentence starts with a capital,
# digit, or quote, so decimals ("0.12 vs") never split mid-number.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def split_into_paragraphs(text, max_chars: int = 350) -> List[str]:
    """Split a prose blob into readable paragraphs.

    LLM-generated fields (problem statements, evidence summaries) arrive
    as one massive paragraph. Existing line breaks are respected; any
    block longer than ``max_chars`` is regrouped into runs of whole
    sentences that fit the budget.
    """
    if not text:
        return []

    paragraphs = []
    for block in str(text).splitlines():
        block = block.strip()
        if not block:
            continue
        if len(block) <= max_chars:
            paragraphs.append(block)
            continue
        current = ""
        for sentence in _SENTENCE_BOUNDARY.split(block):
            if current and len(current) + len(sentence) + 1 > max_chars:
                paragraphs.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            paragraphs.append(current)
    return paragraphs


def normalize_implementation_step(step, index: int) -> Dict[str, str]:
    """Coerce one implementation step into a uniform renderable dict.

    Article recommendations store steps as dicts ({step, effort, owner,
    notes}); social media recommendations store plain strings. The
    renderer must handle both without crashing.
    """
    if isinstance(step, dict):
        return {
            "step": step.get("step", f"Step {index}"),
            "effort": step.get("effort", "") or "",
            "owner": step.get("owner", "") or "",
            "notes": step.get("notes", "") or "",
        }
    return {"step": str(step), "effort": "", "owner": "", "notes": ""}
