"""Evaluate robots.txt rules for configured crawlers."""

import urllib.robotparser
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_CRAWLERS = [
    "OAI-SearchBot",
    "GPTBot",
    "PerplexityBot",
    "Claude-SearchBot",
    "Googlebot",
    "Bingbot",
]


class RobotsChecker:
    """Check whether a crawler is allowed by robots.txt."""

    def __init__(self):
        self.cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    def is_allowed(self, url: str, crawler: str) -> bool:
        """
        Check if a crawler is allowed to access a URL per robots.txt.

        Args:
            url: Full URL to check (e.g., https://www.striim.com/product/oracle-cdc/)
            crawler: Crawler user-agent (e.g., "OAI-SearchBot")

        Returns:
            True if allowed, False if disallowed, True if robots.txt missing (assume allowed)
        """
        try:
            # Extract domain from URL
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            robots_url = f"{domain}/robots.txt"

            # Get or create parser for this domain
            if domain not in self.cache:
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(robots_url)
                try:
                    parser.read()
                except Exception as e:
                    logger.warning(f"Failed to fetch {robots_url}: {e}")
                    # If robots.txt missing, assume allowed
                    parser = None
                self.cache[domain] = parser

            parser = self.cache[domain]
            if parser is None:
                # robots.txt missing/unreachable, assume allowed
                return True

            # Check if crawler is allowed
            return parser.can_fetch(crawler, url)

        except Exception as e:
            logger.error(f"Error checking robots.txt for {url} / {crawler}: {e}")
            # Fail open: if we can't determine, assume allowed
            return True
