"""Display formatting helpers for the dashboard."""

from __future__ import annotations

from typing import Dict

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
