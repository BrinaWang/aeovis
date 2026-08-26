"""Crawler classification for user agents in request logs."""
import re
from typing import Dict, Optional


class CrawlerClassifier:
    """Classify user agents to identify crawler types and AI tools.

    Categorizes user agents into: known_ai_crawler, delegated_agent,
    search_crawler, human_browser, unknown.
    """

    # Known AI crawler patterns (exact matches, case-insensitive)
    KNOWN_AI_CRAWLERS = {
        "oai-searchbot",
        "gptbot",
        "perplexitybot",
        "claude-searchbot",
        "claudebot",
    }

    # Delegated agent patterns (regex, case-insensitive)
    DELEGATED_AGENT_PATTERNS = [
        r"agent-\w+",  # agent-* pattern
        r"chatgpt-user",
        r"perplexity-user",
    ]

    # Known search crawler patterns (exact matches, case-insensitive)
    SEARCH_CRAWLERS = {
        "googlebot",
        "bingbot",
        "slurp",
        "duckduckgo-bot",
    }

    # Model hint patterns
    MODEL_HINT_PATTERNS = [
        r"\(([a-z0-9\-]*(?:claude|gpt)[a-z0-9\-]*)\)",  # (model-name)
        r"[\s\-]([a-z0-9\-]*(?:claude|gpt)[a-z0-9\-]*)",  # - or space-separated
    ]

    def classify(self, user_agent: str) -> Dict:
        """Classify a user agent string.

        Args:
            user_agent: The user agent string to classify.

        Returns:
            A dict with keys:
                - class: One of "known_ai_crawler", "delegated_agent",
                         "search_crawler", "human_browser", "unknown"
                - matched_pattern: The pattern that matched (if any)
                - tool_name: Extracted tool name from user agent (if applicable)
                - model_hint: Extracted model hint (claude-*, gpt-*)
                - known_crawler: Boolean indicating if it's a known crawler
        """
        if not user_agent:
            return {
                "class": "unknown",
                "matched_pattern": None,
                "tool_name": None,
                "model_hint": None,
                "known_crawler": False,
            }

        ua_lower = user_agent.lower()

        # Check known AI crawlers
        for crawler in self.KNOWN_AI_CRAWLERS:
            if crawler in ua_lower:
                model_hint = self._extract_model_hint(user_agent)
                return {
                    "class": "known_ai_crawler",
                    "matched_pattern": crawler,
                    "tool_name": None,
                    "model_hint": model_hint,
                    "known_crawler": True,
                }

        # Check delegated agents
        for pattern in self.DELEGATED_AGENT_PATTERNS:
            match = re.search(pattern, ua_lower)
            if match:
                tool_name = self._extract_tool_name(user_agent, match.group(0))
                model_hint = self._extract_model_hint(user_agent)
                return {
                    "class": "delegated_agent",
                    "matched_pattern": pattern,
                    "tool_name": tool_name,
                    "model_hint": model_hint,
                    "known_crawler": False,
                }

        # Check search crawlers
        for crawler in self.SEARCH_CRAWLERS:
            if crawler in ua_lower:
                return {
                    "class": "search_crawler",
                    "matched_pattern": crawler,
                    "tool_name": None,
                    "model_hint": None,
                    "known_crawler": True,
                }

        # Check for human browser heuristics
        if self._looks_like_browser(ua_lower):
            return {
                "class": "human_browser",
                "matched_pattern": None,
                "tool_name": None,
                "model_hint": None,
                "known_crawler": False,
            }

        # Default to unknown
        return {
            "class": "unknown",
            "matched_pattern": None,
            "tool_name": None,
            "model_hint": None,
            "known_crawler": False,
        }

    def _extract_model_hint(self, user_agent: str) -> Optional[str]:
        """Extract model hints (claude-*, gpt-*) from user agent.

        Args:
            user_agent: The user agent string.

        Returns:
            The extracted model hint, or None if not found.
        """
        ua_lower = user_agent.lower()
        for pattern in self.MODEL_HINT_PATTERNS:
            match = re.search(pattern, ua_lower)
            if match:
                return match.group(1)
        return None

    def _extract_tool_name(self, user_agent: str, matched_pattern: str) -> str:
        """Extract tool name from matched pattern or user agent.

        Args:
            user_agent: The full user agent string.
            matched_pattern: The matched pattern string.

        Returns:
            The extracted tool name.
        """
        # For agent-* patterns, extract the tool name
        if matched_pattern.startswith("agent-"):
            tool_name = matched_pattern.replace("agent-", "")
            return tool_name

        # For chatgpt-user or perplexity-user patterns
        if "chatgpt-user" in matched_pattern.lower():
            return "chatgpt"
        if "perplexity-user" in matched_pattern.lower():
            return "perplexity"

        return matched_pattern

    def _looks_like_browser(self, ua_lower: str) -> bool:
        """Determine if user agent looks like a human browser.

        Args:
            ua_lower: The lowercased user agent string.

        Returns:
            True if it appears to be a human browser, False otherwise.
        """
        browser_indicators = [
            "mozilla",
            "chrome",
            "safari",
            "firefox",
            "edge",
            "opera",
        ]
        return any(indicator in ua_lower for indicator in browser_indicators)
