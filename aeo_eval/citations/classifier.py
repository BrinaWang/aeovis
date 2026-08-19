"""Source classification for citations."""

from __future__ import annotations

from typing import Literal
import logging

logger = logging.getLogger(__name__)


def classify_source(url: str, domain: str) -> Literal[
    "striim_owned", "competitor", "partner_docs", "review_platform",
    "technical_publication", "customer_content", "community_content",
    "analyst_research", "other"
]:
    """
    Classify source category based on URL and domain.

    Args:
        url: Full URL
        domain: Extracted domain

    Returns:
        Source category
    """
    domain_lower = domain.lower()
    url_lower = url.lower()

    # Striim-owned
    if "striim.com" in domain_lower:
        return "striim_owned"

    # Competitors
    competitor_domains = [
        "fivetran.com",
        "confluent.io",
        "kafka.apache.org",
        "oracle.com",
        "qlik.com",
        "estuary.dev",
        "aws.amazon.com",
    ]
    if any(comp in domain_lower for comp in competitor_domains):
        return "competitor"

    # Partner/integration docs
    if "docs." in domain_lower or "documentation" in domain_lower:
        return "partner_docs"

    # Review platforms
    if any(x in domain_lower for x in ["g2.com", "capterra.com", "gartner.com", "forrester.com"]):
        return "review_platform"

    # Technical publications
    if any(x in domain_lower for x in ["medium.com", "dev.to", "github.com", "stackoverflow.com"]):
        return "technical_publication"

    # Community/forums
    if any(x in domain_lower for x in ["reddit.com", "slack.com", "discord.com"]):
        return "community_content"

    # Analyst research
    if any(x in domain_lower for x in ["gartner", "forrester", "analyst"]):
        return "analyst_research"

    return "other"
