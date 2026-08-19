from __future__ import annotations

import re
from typing import List

from aeo_eval.analysis.llm_extractor import extract_with_claude


def extract_brand_mentions(text: str, brand_names: List[str] | None = None) -> List[str]:
    """Return brand names found in a text block using a simple case-insensitive match."""
    if brand_names is None:
        brand_names = ["Striim", "Fivetran", "Confluent", "Kafka", "Oracle GoldenGate"]

    normalized = text.lower()
    matches: List[str] = []
    for brand in brand_names:
        if brand.lower() in normalized:
            matches.append(brand)
    return matches


def extract_response(
    response_text: str,
    engine,  # BaseEngine instance
    competitors: list[str] | None = None,
) -> dict:
    """
    Extract brands, positions, claims from a response.

    Args:
        response_text: Raw response text
        engine: BaseEngine instance with structured output support
        competitors: List of competitor names to detect

    Returns:
        Dict with brand mentions, claims, positions, sentiment
    """
    if competitors is None:
        competitors = ["Fivetran", "Confluent", "Kafka", "Oracle GoldenGate", "AWS DMS"]

    # Extract brands (deterministic)
    brand_mentions = extract_brand_mentions(response_text, ["Striim"] + competitors)

    # Extract position, claims, sentiment (LLM-based)
    llm_output, analysis_cost = extract_with_claude(engine, response_text, competitors)

    if llm_output is None:
        # Fallback to basic extraction if LLM fails
        return {
            "brands_found": brand_mentions,
            "striim_mentioned": "Striim" in brand_mentions,
            "striim_position": None,
            "competitors": [],
            "striim_claims": [],
            "citations": [],
            "sentiment": "neutral",
            "confidence": 0.0,
            "flagged_for_review": True,
            "analysis_cost": 0.0,
        }

    # Extract citations from two sources:
    # 1. Citations explicitly supporting Striim claims
    claim_citations = [
        c.supporting_citation_url
        for c in llm_output.striim_claims
        if c.supporting_citation_url
    ]

    # 2. All URLs in the response (for complete citation tracking)
    all_urls = re.findall(r'https?://[^\s)]+', response_text)

    # Combine: use all URLs as citations, but ensure claim citations are included
    citations = list(dict.fromkeys(all_urls))  # Remove duplicates while preserving order

    return {
        "brands_found": brand_mentions,
        "striim_mentioned": "Striim" in brand_mentions,
        "striim_position": llm_output.striim_position,
        "competitors": [(c.name, c.position) for c in llm_output.competitors],
        "striim_claims": [(c.text, c.sentiment) for c in llm_output.striim_claims],
        "citations": citations,
        "sentiment": llm_output.general_sentiment_toward_striim,
        "confidence": llm_output.extraction_confidence,
        "flagged_for_review": llm_output.flagged_for_review,
        "analysis_cost": analysis_cost,
    }
