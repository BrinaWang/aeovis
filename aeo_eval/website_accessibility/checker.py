"""Main website accessibility checker orchestrating all checks."""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional

from .robots_checker import RobotsChecker, DEFAULT_CRAWLERS
from .http_checker import HttpChecker
from .extractability import ExtractabilityChecker

logger = logging.getLogger(__name__)


class WebsiteAccessibilityChecker:
    """Orchestrate all website accessibility checks."""

    def __init__(self):
        """Initialize the orchestrator with individual checkers."""
        self.robots_checker = RobotsChecker()
        self.http_checker = HttpChecker()
        self.extractability_checker = ExtractabilityChecker()

    def check_pages(
        self,
        important_pages: List[str],
        crawlers: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Check accessibility of pages for specified crawlers.

        Orchestrates RobotsChecker, HttpChecker, and ExtractabilityChecker
        to produce comprehensive accessibility results.

        Args:
            important_pages: List of URLs to check
            crawlers: List of crawler user-agents to check. If None, uses DEFAULT_CRAWLERS

        Returns:
            List of dicts ready to insert into website_checks table with keys:
            - id: Unique identifier
            - striim_url: The URL checked
            - crawler: The crawler user-agent
            - robots_allowed: Boolean (0/1) whether robots.txt allows crawler
            - in_sitemap: Boolean (0/1) placeholder (always None for now)
            - http_status: HTTP status code or None if fetch failed
            - response_time_ms: Response time in milliseconds
            - noindex: Boolean (0/1) whether page has noindex directive
            - canonical_url: Canonical URL from page metadata
            - result: Classification of accessibility (string)
            - check_timestamp: ISO format timestamp
        """
        if crawlers is None:
            crawlers = DEFAULT_CRAWLERS

        results = []

        # First pass: check HTTP metadata and extractability once per URL
        url_metadata = {}
        for url in important_pages:
            try:
                http_result = self.http_checker.check_page(url)
                extract_result = self.extractability_checker.check_extractability(url)
                url_metadata[url] = {
                    "http": http_result,
                    "extract": extract_result,
                }
            except Exception as e:
                logger.error(f"Error checking URL {url}: {e}")
                url_metadata[url] = {
                    "http": {
                        "status_code": None,
                        "response_time_ms": None,
                        "noindex": False,
                        "canonical_url": None,
                        "fetch_error": str(e),
                    },
                    "extract": {
                        "result": "fetch_failed",
                    },
                }

        # Second pass: check robots.txt for each (URL, crawler) pair
        for url in important_pages:
            http_meta = url_metadata[url]["http"]
            extract_meta = url_metadata[url]["extract"]

            for crawler in crawlers:
                try:
                    robots_allowed = self.robots_checker.is_allowed(url, crawler)

                    # Classify the result
                    result_classification = self._classify_result(
                        http_meta, robots_allowed, extract_meta
                    )

                    # Build record for database
                    check_record = {
                        "id": str(uuid.uuid4()),
                        "striim_url": url,
                        "crawler": crawler,
                        "robots_allowed": 1 if robots_allowed else 0,
                        "in_sitemap": None,  # TODO: implement sitemap checking
                        "http_status": http_meta.get("status_code"),
                        "response_time_ms": int(http_meta.get("response_time_ms", 0)) if http_meta.get("response_time_ms") else None,
                        "noindex": 1 if http_meta.get("noindex") else 0,
                        "canonical_url": http_meta.get("canonical_url"),
                        "result": result_classification,
                        "check_timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                    results.append(check_record)

                except Exception as e:
                    logger.error(f"Error checking {url} for {crawler}: {e}")
                    # Add an error record
                    check_record = {
                        "id": str(uuid.uuid4()),
                        "striim_url": url,
                        "crawler": crawler,
                        "robots_allowed": None,
                        "in_sitemap": None,
                        "http_status": None,
                        "response_time_ms": None,
                        "noindex": None,
                        "canonical_url": None,
                        "result": "check_failed",
                        "check_timestamp": datetime.utcnow().isoformat() + "Z",
                    }
                    results.append(check_record)

        return results

    def _classify_result(
        self,
        http_result: Dict,
        robots_allowed: bool,
        extract_result: Dict,
    ) -> str:
        """
        Classify the overall accessibility result based on check outcomes.

        Args:
            http_result: Result from HttpChecker.check_page()
            robots_allowed: Result from RobotsChecker.is_allowed()
            extract_result: Result from ExtractabilityChecker.check_extractability()

        Returns:
            Classification string: "publicly_accessible", "blocked_by_robots",
            "http_error", "noindex_set", "poorly_extractable", "fetch_failed", etc.
        """
        # Check for fetch errors first
        if http_result.get("fetch_error"):
            status = http_result.get("status_code")
            if status is None:
                return "fetch_failed"
            elif 400 <= status < 500:
                return "http_error_4xx"
            elif 500 <= status < 600:
                return "http_error_5xx"
            return "http_error"

        # Check robots.txt blocking
        if not robots_allowed:
            return "blocked_by_robots"

        # Check noindex directive
        if http_result.get("noindex"):
            return "noindex_set"

        # Check HTTP status
        status = http_result.get("status_code")
        if status is None:
            return "fetch_failed"
        elif status != 200:
            if 400 <= status < 500:
                return "http_error_4xx"
            elif 500 <= status < 600:
                return "http_error_5xx"
            return f"http_status_{status}"

        # Check extractability
        extractability = extract_result.get("result", "unknown")
        if extractability == "fetch_failed":
            return "fetch_failed"
        elif extractability == "poorly_extractable":
            return "poorly_extractable"

        # All checks passed
        return "publicly_accessible"
