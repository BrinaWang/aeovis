"""Tests for website accessibility checks."""

import pytest
from unittest.mock import MagicMock, patch
from aeo_eval.website_accessibility import (
    RobotsChecker,
    HttpChecker,
    ExtractabilityChecker,
    WebsiteAccessibilityChecker,
)


def test_robots_checker_allows_known_crawler(mocker):
    """Test that RobotsChecker correctly evaluates robots.txt rules."""
    checker = RobotsChecker()

    # Mock the RobotFileParser to simulate an allowed crawler
    mock_parser = MagicMock()
    mock_parser.can_fetch.return_value = True
    mocker.patch(
        'aeo_eval.website_accessibility.robots_checker.urllib.robotparser.RobotFileParser',
        return_value=mock_parser
    )

    result = checker.is_allowed("https://www.striim.com/product/oracle-cdc/", "OAI-SearchBot")
    # Verify actual value, not just type
    assert result is True


def test_robots_checker_handles_missing_robots_txt(mocker):
    """Test graceful handling when robots.txt doesn't exist."""
    checker = RobotsChecker()

    # Mock read() to raise an exception (robots.txt missing)
    mock_parser = MagicMock()
    mock_parser.read.side_effect = Exception("404 - robots.txt not found")
    mocker.patch(
        'aeo_eval.website_accessibility.robots_checker.urllib.robotparser.RobotFileParser',
        return_value=mock_parser
    )

    result = checker.is_allowed("https://example-no-robots.test/page/", "Googlebot")
    # Should fail open (True) when robots.txt is missing
    assert result is True


def test_robots_checker_caches_domain_parsers():
    """Test that parsers are cached per domain."""
    checker = RobotsChecker()
    url1 = "https://www.striim.com/product/oracle-cdc/"
    url2 = "https://www.striim.com/docs/snowflake/"
    crawler = "Googlebot"

    result1 = checker.is_allowed(url1, crawler)
    result2 = checker.is_allowed(url2, crawler)

    # Both should use same cached parser
    assert len(checker.cache) == 1
    assert result1 == result2


def test_http_checker_returns_status_and_metadata():
    """Test that HttpChecker fetches page and extracts metadata."""
    checker = HttpChecker()
    result = checker.check_page("https://www.striim.com/product/oracle-cdc/")

    assert "status_code" in result
    assert "response_time_ms" in result
    assert isinstance(result["status_code"], int)
    assert isinstance(result["response_time_ms"], (int, float))


def test_extractability_checker_returns_ratio():
    """Test that ExtractabilityChecker returns extraction metrics."""
    checker = ExtractabilityChecker()
    result = checker.check_extractability("https://www.striim.com/product/oracle-cdc/")

    assert "extraction_ratio" in result
    assert "word_count" in result
    assert isinstance(result["extraction_ratio"], (int, float))
    assert result["extraction_ratio"] >= 0


def test_website_accessibility_checker_orchestrates_checks():
    """Test that WebsiteAccessibilityChecker orchestrates all three checkers."""
    checker = WebsiteAccessibilityChecker()
    urls = ["https://www.striim.com/product/oracle-cdc/"]
    crawlers = ["Googlebot", "OAI-SearchBot"]
    results = checker.check_pages(urls, crawlers)

    # Should have one result per (URL, crawler) pair
    assert len(results) == len(urls) * len(crawlers)

    # Verify required fields in each result
    for result in results:
        assert "id" in result
        assert "striim_url" in result
        assert "crawler" in result
        assert "robots_allowed" in result
        assert "http_status" in result
        assert "response_time_ms" in result
        assert "noindex" in result
        assert "canonical_url" in result
        assert "result" in result
        assert "check_timestamp" in result

        # Verify field types
        assert isinstance(result["id"], str)
        assert isinstance(result["striim_url"], str)
        assert isinstance(result["crawler"], str)
        assert result["result"] in [
            "publicly_accessible",
            "blocked_by_robots",
            "noindex_set",
            "http_error",
            "http_error_4xx",
            "http_error_5xx",
            "poorly_extractable",
            "fetch_failed",
            "check_failed",
        ] or result["result"].startswith("http_status_")

        # Verify that both crawlers are represented
        crawler_names = {r["crawler"] for r in results}
        assert crawler_names == set(crawlers)
