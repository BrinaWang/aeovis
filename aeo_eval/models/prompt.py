"""Input-side data models.

``Prompt`` is the live model: one row of ``question.json`` and one row of
the ``prompts`` table. ``Citation``, ``EngineResponse`` and
``ExtractionResult`` are earlier-generation shapes that predate
``RunResult`` / ``ResponseAnalysisOutput``; they are still exported from
``aeo_eval.models`` for compatibility but nothing in the pipeline,
dashboard or tests constructs them. Prefer the models in ``result.py`` and
``analysis.py`` for new code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Prompt:
    """One buyer question.

    Attributes:
        id: Stable identifier (e.g. ``gen-001``). It is the join key
            between ``raw_responses.prompt_id`` and the ``prompts`` table,
            so it must be unique across the dataset and stable across runs
            for trends to line up.
        prompt: The question text sent verbatim to the answer engine.
        topic: Grouping used for by-topic metrics and gap detection.
        persona: Buyer persona label; keys into ``personas.json``.
        intent: ``commercial`` or ``educational`` in the shipped dataset.
        priority: ``high`` / ``medium`` / ``low`` (lower-case in the shipped
            dataset). Gap thresholds capitalise it before lookup; the
            evaluator's ``--priority`` filter compares it verbatim.
        enabled: Always True after ``load_prompts``, which drops disabled
            questions.
        variant_of: Optional id of the question this one rephrases.
        tags: Free-form labels; not used by any computation.
    """
    id: str
    prompt: str
    topic: str
    persona: str
    intent: str
    priority: str
    enabled: bool = True
    variant_of: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class Citation:
    """Legacy citation shape (unused; see module docstring)."""
    url: str
    normalized_url: Optional[str] = None
    domain: Optional[str] = None


@dataclass
class EngineResponse:
    """Legacy engine response shape superseded by ``RunResult`` (unused)."""
    prompt_id: str
    engine: str
    model: str
    raw_response: str
    citations: List[Citation] = field(default_factory=list)
    latency_ms: int = 0
    estimated_cost: float = 0.0
    status: str = "success"
    error: Optional[str] = None


@dataclass
class ExtractionResult:
    """Legacy extraction shape superseded by ``LLMExtractionOutput`` (unused)."""
    prompt_id: str
    striim_mentioned: bool = False
    striim_recommended: bool = False
    competitors: List[str] = field(default_factory=list)
    striim_position: Optional[int] = None
    confidence: float = 0.0
