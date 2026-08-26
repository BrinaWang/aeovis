"""Tests for request log parser and crawler classifier."""
import pytest
from aeo_eval.request_logs import RequestLogParser, CrawlerClassifier, RequestLogAnalyzer


def test_parser_reads_json_lines():
    """Test that parser reads and validates JSON lines correctly."""
    parser = RequestLogParser()
    line = '{"timestamp":"2026-08-04T18:42:12Z","host":"www.striim.com","path":"/product/oracle-cdc/","status_code":200,"user_agent":"OAI-SearchBot/1.0"}'
    result = parser.parse_json_line(line)
    assert result is not None
    assert result["host"] == "www.striim.com"
    assert result["status_code"] == 200
    assert "user_agent" in result
    assert result["user_agent"] == "OAI-SearchBot/1.0"


def test_parser_normalizes_fields():
    """Test that parser normalizes paths by removing query parameters."""
    parser = RequestLogParser()
    line = '{"timestamp":"2026-08-04T18:42:12Z","host":"www.striim.com","path":"/product/oracle-cdc/?param=value","status_code":200,"user_agent":"OAI-SearchBot/1.0"}'
    result = parser.parse_json_line(line)
    assert result is not None
    assert result["normalized_path"] == "/product/oracle-cdc/"


def test_classifier_identifies_known_ai_crawlers():
    """Test that classifier identifies known AI crawlers."""
    classifier = CrawlerClassifier()
    result = classifier.classify("OAI-SearchBot/1.0")
    assert result["class"] == "known_ai_crawler"
    assert result["known_crawler"] is True


def test_classifier_identifies_delegated_agents():
    """Test that classifier identifies delegated agents."""
    classifier = CrawlerClassifier()
    result = classifier.classify("agent-cursor (claude-sonnet-4)")
    assert result["class"] == "delegated_agent"
    assert "cursor" in result.get("tool_name", "").lower()


def test_analyzer_detects_failures():
    """Test that analyzer detects failures and normalizes records."""
    analyzer = RequestLogAnalyzer()
    records = [{
        "id": "1",
        "timestamp": "2026-08-04T18:42:12Z",
        "host": "www.striim.com",
        "path": "/product/oracle-cdc/",
        "status_code": 403,
        "user_agent": "OAI-SearchBot/1.0",
        "response_time_ms": 24,
        "normalized_path": "/product/oracle-cdc/",
    }]
    results = analyzer.analyze(records)
    assert len(results) == 1
    assert results[0]["crawler"] == "oai-searchbot"
    assert results[0]["http_status"] == 403
    assert results[0]["edge_action"] == "blocked"
    assert results[0]["ua_classification"]["class"] == "known_ai_crawler"
