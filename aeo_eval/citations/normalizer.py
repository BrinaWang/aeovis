"""URL normalization and domain extraction."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse
import logging

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """
    Normalize URL to canonical form.

    Rules:
    - Remove query params and fragments
    - Remove trailing slash
    - Convert to lowercase
    - Decode URL encoding
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)
        # Reconstruct without query and fragment
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",  # params
            "",  # query
            ""   # fragment
        ))
        return normalized
    except Exception as e:
        logger.warning(f"Failed to normalize URL {url}: {e}")
        return url


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception as e:
        logger.warning(f"Failed to extract domain from {url}: {e}")
        return ""


def extract_path(url: str) -> str:
    """Extract path from URL."""
    try:
        parsed = urlparse(url)
        return parsed.path
    except Exception as e:
        logger.warning(f"Failed to extract path from {url}: {e}")
        return ""
