"""Extractability checker for content from Striim pages."""

import httpx
import time
import logging
from typing import Dict, Optional
import trafilatura
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

USER_AGENT = "striim-aeo-monitor/1.0 (internal AEO research)"


class ExtractabilityChecker:
    """Check extractability of content from URLs."""

    def __init__(self, timeout_seconds: int = 15, rate_limit_rps: float = 0.5):
        """Initialize the ExtractabilityChecker.

        Args:
            timeout_seconds: HTTP request timeout in seconds
            rate_limit_rps: Rate limit in requests per second per domain
        """
        self.timeout_seconds = timeout_seconds
        self.rate_limit_rps = rate_limit_rps
        self.last_request_time: Dict[str, float] = {}

    def _rate_limit(self, domain: str):
        """Apply rate limiting per domain."""
        parsed = urlparse(domain) if domain.startswith("http") else urlparse(f"https://{domain}")
        domain_key = f"{parsed.scheme}://{parsed.netloc}"

        if domain_key in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain_key]
            wait_time = (1.0 / self.rate_limit_rps) - elapsed
            if wait_time > 0:
                time.sleep(wait_time)

        self.last_request_time[domain_key] = time.time()

    def check_extractability(self, url: str) -> Dict:
        """
        Check extractability of content from a URL.

        Args:
            url: Full URL to check

        Returns:
            Dict with keys:
            - url: The URL checked
            - extraction_ratio: float (extracted_chars / raw_html_bytes)
            - word_count: int (number of words in extracted text)
            - requires_js_render: bool (always False for basic extraction)
            - result: str ("well_extractable", "poorly_extractable", "fetch_failed")
            - raw_html_bytes: int (size of raw HTML in bytes)
            - extracted_text_chars: int (number of characters in extracted text)
            - fetch_error: str or None (error message if fetch failed)
        """
        result = {
            "url": url,
            "extraction_ratio": 0.0,
            "word_count": 0,
            "requires_js_render": False,
            "result": "fetch_failed",
            "raw_html_bytes": 0,
            "extracted_text_chars": 0,
            "fetch_error": None,
        }

        try:
            self._rate_limit(url)

            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()

            raw_html = response.content
            result["raw_html_bytes"] = len(raw_html)

            # Extract text using trafilatura
            extracted_text = trafilatura.extract(response.text, include_comments=False)

            if extracted_text:
                result["extracted_text_chars"] = len(extracted_text)

                # Calculate word count
                word_count = len(extracted_text.split())
                result["word_count"] = word_count

                # Calculate extraction ratio
                if result["raw_html_bytes"] > 0:
                    result["extraction_ratio"] = result["extracted_text_chars"] / result["raw_html_bytes"]

                # Classify extractability
                # poorly_extractable if word_count < 300 OR ratio < 0.05
                if word_count < 300 or result["extraction_ratio"] < 0.05:
                    result["result"] = "poorly_extractable"
                else:
                    result["result"] = "well_extractable"
            else:
                # No text extracted
                result["result"] = "poorly_extractable"
                result["word_count"] = 0
                result["extracted_text_chars"] = 0
                if result["raw_html_bytes"] > 0:
                    result["extraction_ratio"] = 0.0

        except Exception as e:
            result["fetch_error"] = str(e)
            result["result"] = "fetch_failed"
            logger.error(f"Error checking extractability for {url}: {e}")

        return result
