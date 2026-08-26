"""Check HTTP status, response time, and metadata (canonical, noindex, sitemap)."""

import httpx
import time
import logging
from typing import Dict, Optional, List
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

USER_AGENT = "striim-aeo-monitor/1.0 (internal AEO research)"

class HttpChecker:
    """Check HTTP metadata for a Striim page."""

    def __init__(self, timeout_seconds: int = 15, rate_limit_rps: float = 0.5):
        self.timeout_seconds = timeout_seconds
        self.rate_limit_rps = rate_limit_rps
        self.last_request_time: Dict[str, float] = {}

    def _rate_limit(self, domain: str):
        """Apply rate limiting per domain."""
        from urllib.parse import urlparse
        parsed = urlparse(domain) if domain.startswith("http") else urlparse(f"https://{domain}")
        domain_key = f"{parsed.scheme}://{parsed.netloc}"

        if domain_key in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain_key]
            wait_time = (1.0 / self.rate_limit_rps) - elapsed
            if wait_time > 0:
                time.sleep(wait_time)

        self.last_request_time[domain_key] = time.time()

    def check_page(self, url: str) -> Dict:
        """
        Check HTTP status and metadata for a page.

        Args:
            url: Full URL to check

        Returns:
            Dict with keys:
            - status_code: HTTP status
            - response_time_ms: Round-trip time
            - noindex: bool (True if page has noindex meta tag or header)
            - canonical_url: str or None
            - content_length: bytes
            - fetch_error: str or None (if request failed)
        """
        result = {
            "url": url,
            "status_code": None,
            "response_time_ms": None,
            "noindex": False,
            "canonical_url": None,
            "content_length": 0,
            "fetch_error": None,
        }

        try:
            self._rate_limit(url)

            start = time.time()
            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=self.timeout_seconds,
            )
            elapsed_ms = (time.time() - start) * 1000

            result["status_code"] = response.status_code
            result["response_time_ms"] = elapsed_ms
            result["content_length"] = len(response.content)

            # Parse HTML for metadata
            if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
                soup = BeautifulSoup(response.text, "html.parser")

                # Check for noindex
                noindex_meta = soup.find("meta", attrs={"name": "robots", "content": lambda x: x and "noindex" in x})
                if noindex_meta or "noindex" in response.headers.get("x-robots-tag", ""):
                    result["noindex"] = True

                # Get canonical URL
                canonical = soup.find("link", attrs={"rel": "canonical"})
                if canonical and canonical.get("href"):
                    result["canonical_url"] = canonical["href"]
                elif "content-location" in response.headers:
                    result["canonical_url"] = response.headers["content-location"]

        except Exception as e:
            result["fetch_error"] = str(e)
            logger.error(f"Error fetching {url}: {e}")

        return result
