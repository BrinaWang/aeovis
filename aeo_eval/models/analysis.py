"""Data models for response analysis outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional


@dataclass
class ResponseAnalysisOutput:
    """Module 3 output: Response analysis data.

    Represents extracted analysis from a raw response including brands,
    claims, citations, and confidence scores for quality control.
    """
    raw_response_id: str
    striim_mentioned: bool
    striim_recommended: bool
    striim_position: Optional[int] = None
    brands_found: Optional[str] = None  # JSON string
    claims: Optional[str] = None  # JSON string
    citations: Optional[str] = None  # JSON string
    extraction_confidence: float = 0.0
    flagged_for_review: bool = False


@dataclass
class Claim:
    """A single claim extracted from a response."""
    text: str
    sentiment: Literal["positive", "neutral", "negative"]
    confidence: float  # 0.0-1.0
    supporting_citation_url: Optional[str] = None


@dataclass
class BrandMention:
    """Brand mention with position and recommendation status."""
    name: str
    position: Optional[int]  # None for unordered, integer for ordered (1=top)
    is_recommended: bool
    confidence: float  # 0.0-1.0


@dataclass
class LLMExtractionOutput:
    """Output from LLM-based extraction."""
    striim_position: Optional[int]  # Position of Striim in response (1, 2, 3, etc., or None)
    competitors: List[BrandMention]  # Competitors with positions
    striim_claims: List[Claim]
    general_sentiment_toward_striim: Literal["positive", "neutral", "negative"]
    extraction_confidence: float  # Overall confidence (0.0-1.0)
    flagged_for_review: bool  # True if confidence < 0.65 or ambiguous


@dataclass
class StructuredCallResult:
    """Parsed structured-output call plus its token usage and cost."""
    data: Dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
