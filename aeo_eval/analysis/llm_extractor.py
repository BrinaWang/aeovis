"""LLM-based extraction of brands, positions, claims, and sentiment."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

from aeo_eval.models.analysis import LLMExtractionOutput, Claim, BrandMention

logger = logging.getLogger(__name__)


EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "striim_position": {"type": ["integer", "null"]},
        "competitors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "position": {"type": ["integer", "null"]},
                    "is_recommended": {"type": "boolean"},
                },
                "required": ["name", "position", "is_recommended"],
            },
        },
        "striim_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "sentiment": {"enum": ["positive", "neutral", "negative"]},
                    "confidence": {"type": "number"},
                    "supporting_citation_url": {"type": ["string", "null"]},
                },
                "required": ["text", "sentiment", "confidence", "supporting_citation_url"],
            },
        },
        "general_sentiment_toward_striim": {"enum": ["positive", "neutral", "negative"]},
        "extraction_confidence": {"type": "number"},
        "flagged_for_review": {"type": "boolean"},
    },
    "required": [
        "striim_position",
        "competitors",
        "striim_claims",
        "general_sentiment_toward_striim",
        "extraction_confidence",
        "flagged_for_review",
    ],
}


def build_extraction_prompt(response_text: str, competitors: list[str]) -> str:
    """
    Build a prompt for Claude to extract brands, positions, and claims.

    Args:
        response_text: The raw response from an answer engine
        competitors: List of competitor names to look for

    Returns:
        Prompt string
    """
    competitors_str = ", ".join(competitors)
    return f"""Analyze this AI-generated answer for mentions of Striim and competitors.

Answer:
{response_text}

Extract and return JSON with:
1. striim_position: null if Striim not mentioned, or the position number (1=first, 2=second, etc.) if mentioned in an ordered list. Use null for unordered product lists.
2. competitors: Array of {{name, position, is_recommended}} for each competitor mentioned. Position null if unordered.
3. striim_claims: Array of {{text, sentiment, confidence, supporting_citation_url}} for claims about Striim. Sentiment: "positive", "neutral", or "negative". Confidence 0.0-1.0. Use "positive" for recommendations, "negative" for criticism, "neutral" for factual statements.
4. general_sentiment_toward_striim: Overall sentiment ("positive", "neutral", or "negative")
5. extraction_confidence: Your confidence in the extraction (0.0-1.0). Lower if response is ambiguous or poorly structured.
6. flagged_for_review: true if confidence < 0.65 or any result is ambiguous.

Competitors to watch for: {competitors_str}

Return ONLY valid JSON, no markdown, no explanation."""


def extract_with_claude(
    engine,  # BaseEngine instance with structured output support
    response_text: str,
    competitors: list[str],
) -> Tuple[Optional[LLMExtractionOutput], float]:
    """
    Call Claude API with structured output to extract brands and claims.

    Args:
        engine: An initialized BaseEngine (e.g., ClaudeEngine)
        response_text: Raw response from answer engine
        competitors: Competitor names to detect

    Returns:
        Tuple of (LLMExtractionOutput or None if extraction fails, cost in dollars).
    """
    prompt = build_extraction_prompt(response_text, competitors)

    try:
        call = engine.run_with_structured_output(prompt, EXTRACTION_SCHEMA)
        result = call.data

        if "raw_response" in result:
            # The engine's upstream JSON parse failed and fell back to
            # {"raw_response": <text>} instead of raising; none of the
            # expected extraction keys are present. Flag for review with
            # zero confidence rather than silently returning an
            # unflagged, all-defaults "clean" extraction. Cost is still
            # tracked since the call itself succeeded and was billed.
            logger.warning(
                "Structured extraction returned unparsed raw_response; "
                "flagging for review."
            )
            return (
                LLMExtractionOutput(
                    striim_position=None,
                    competitors=[],
                    striim_claims=[],
                    general_sentiment_toward_striim="neutral",
                    extraction_confidence=0.0,
                    flagged_for_review=True,
                ),
                call.cost,
            )

        # Convert dict to LLMExtractionOutput
        competitors_list = [
            BrandMention(
                name=c["name"],
                position=c["position"],
                is_recommended=c.get("is_recommended", False),
                confidence=1.0,  # Extracted by LLM; assume high confidence
            )
            for c in result.get("competitors", [])
        ]

        claims_list = [
            Claim(
                text=claim["text"],
                sentiment=claim["sentiment"],
                confidence=claim["confidence"],
                supporting_citation_url=claim.get("supporting_citation_url"),
            )
            for claim in result.get("striim_claims", [])
        ]

        return (
            LLMExtractionOutput(
                striim_position=result.get("striim_position"),
                competitors=competitors_list,
                striim_claims=claims_list,
                general_sentiment_toward_striim=result.get(
                    "general_sentiment_toward_striim", "neutral"
                ),
                extraction_confidence=result.get("extraction_confidence", 0.5),
                flagged_for_review=result.get("flagged_for_review", False),
            ),
            call.cost,
        )
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return None, 0.0
