"""Tests for RandomMockEngine mock data generator methods."""
from datetime import datetime, timedelta
from aeo_eval.engine.mock_engine import RandomMockEngine


def test_generate_mock_crawler_logs_default_count():
    """Test that generate_mock_crawler_logs produces default count of 50 records."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs()
    assert len(logs) == 50


def test_generate_mock_crawler_logs_custom_count():
    """Test that generate_mock_crawler_logs respects custom count parameter."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=25)
    assert len(logs) == 25


def test_generate_mock_crawler_logs_structure():
    """Test that generated logs have all required fields."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=10)

    required_fields = {
        "id", "timestamp", "host", "path", "status_code",
        "user_agent", "response_time_ms", "normalized_path"
    }

    for log in logs:
        assert isinstance(log, dict)
        assert required_fields.issubset(set(log.keys())), \
            f"Log missing fields: {required_fields - set(log.keys())}"


def test_generate_mock_crawler_logs_field_types():
    """Test that generated log fields have correct types."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=10)

    for log in logs:
        assert isinstance(log["id"], str)
        assert isinstance(log["timestamp"], str)
        assert isinstance(log["host"], str)
        assert isinstance(log["path"], str)
        assert isinstance(log["status_code"], int)
        assert isinstance(log["user_agent"], str)
        assert isinstance(log["response_time_ms"], int)
        assert isinstance(log["normalized_path"], str)


def test_generate_mock_crawler_logs_host_distribution():
    """Test that hosts are mostly www.striim.com with some www.example.com."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=100)

    striim_count = sum(1 for log in logs if log["host"] == "www.striim.com")
    example_count = sum(1 for log in logs if log["host"] == "www.example.com")

    # With 87.5% distribution, at least 70 should be striim, at most 30 example
    assert striim_count >= 70, f"Expected ~87.5% striim, got {striim_count}%"
    assert example_count <= 30, f"Expected ~12.5% example, got {example_count}%"


def test_generate_mock_crawler_logs_valid_paths():
    """Test that generated logs use valid paths."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=50)

    valid_paths = {"/product/", "/docs/", "/blog/", "/solutions/", "/case-studies/"}

    for log in logs:
        assert log["path"] in valid_paths
        assert log["normalized_path"] == log["path"].rstrip("/")


def test_generate_mock_crawler_logs_status_code_distribution():
    """Test that status codes follow expected distribution."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=200)

    status_counts = {}
    for log in logs:
        code = log["status_code"]
        status_counts[code] = status_counts.get(code, 0) + 1

    # Verify all status codes are expected
    assert set(status_counts.keys()).issubset({200, 403, 429, 500})

    # Verify approximate distribution (with tolerance)
    total = sum(status_counts.values())
    assert status_counts.get(200, 0) / total > 0.50  # ~60%
    assert status_counts.get(403, 0) / total > 0.10  # ~20%
    assert status_counts.get(429, 0) / total < 0.15  # ~10%
    assert status_counts.get(500, 0) / total < 0.15  # ~10%


def test_generate_mock_crawler_logs_valid_crawlers():
    """Test that generated logs use valid crawler names."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=50)

    valid_crawlers = {
        "OAI-SearchBot", "PerplexityBot", "Claude-SearchBot",
        "Googlebot", "GPTBot", "Bingbot"
    }

    for log in logs:
        assert log["user_agent"] in valid_crawlers


def test_generate_mock_crawler_logs_realistic_timestamps():
    """Test that generated timestamps are within last 90 days."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=50)

    now = datetime.now()
    ninety_days_ago = now - timedelta(days=90)

    for log in logs:
        timestamp = datetime.fromisoformat(log["timestamp"])
        assert ninety_days_ago <= timestamp <= now


def test_generate_mock_crawler_logs_response_time_range():
    """Test that response times are in valid range."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=50)

    for log in logs:
        assert 10 <= log["response_time_ms"] <= 500


def test_generate_mock_crawler_logs_unique_ids():
    """Test that generated log IDs are unique."""
    engine = RandomMockEngine({})
    logs = engine.generate_mock_crawler_logs(count=100)

    ids = [log["id"] for log in logs]
    assert len(ids) == len(set(ids)), "Generated IDs are not unique"


def test_generate_mock_website_checks_default_count():
    """Test that generate_mock_website_checks produces default count of 30 records."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks()
    assert len(checks) == 30


def test_generate_mock_website_checks_custom_count():
    """Test that generate_mock_website_checks respects custom count parameter."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=15)
    assert len(checks) == 15


def test_generate_mock_website_checks_structure():
    """Test that generated checks have all required fields."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=10)

    required_fields = {
        "id", "striim_url", "crawler", "robots_allowed", "http_status",
        "response_time_ms", "noindex", "canonical_url", "result", "check_timestamp"
    }

    for check in checks:
        assert isinstance(check, dict)
        assert required_fields.issubset(set(check.keys())), \
            f"Check missing fields: {required_fields - set(check.keys())}"


def test_generate_mock_website_checks_field_types():
    """Test that generated check fields have correct types."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=10)

    for check in checks:
        assert isinstance(check["id"], str)
        assert isinstance(check["striim_url"], str)
        assert isinstance(check["crawler"], str)
        assert isinstance(check["robots_allowed"], bool)
        assert isinstance(check["http_status"], int)
        assert isinstance(check["response_time_ms"], int)
        assert isinstance(check["noindex"], bool)
        assert isinstance(check["canonical_url"], str)
        assert isinstance(check["result"], str)
        assert isinstance(check["check_timestamp"], str)


def test_generate_mock_website_checks_valid_urls():
    """Test that generated checks use valid striim URLs."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=30)

    valid_urls = {
        "/product/oracle-cdc/",
        "/docs/oracle-to-snowflake/",
        "/blog/cdc-guide/",
        "/docs/snowflake/",
        "/solutions/data-integration/",
        "/case-studies/",
    }

    for check in checks:
        assert check["striim_url"] in valid_urls
        assert check["canonical_url"].startswith("https://www.striim.com")
        assert check["striim_url"] in check["canonical_url"]


def test_generate_mock_website_checks_valid_crawlers():
    """Test that generated checks use valid crawler names."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=30)

    valid_crawlers = {
        "OAI-SearchBot", "PerplexityBot", "Claude-SearchBot",
        "Googlebot", "GPTBot", "Bingbot"
    }

    for check in checks:
        assert check["crawler"] in valid_crawlers


def test_generate_mock_website_checks_valid_results():
    """Test that generated checks use valid result values."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=50)

    valid_results = {
        "publicly_accessible", "blocked_by_robots",
        "poorly_extractable", "http_error_4xx"
    }

    for check in checks:
        assert check["result"] in valid_results


def test_generate_mock_website_checks_result_distribution():
    """Test that results follow expected distribution."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=300)

    result_counts = {}
    for check in checks:
        result = check["result"]
        result_counts[result] = result_counts.get(result, 0) + 1

    # Verify approximate distribution (with tolerance)
    total = sum(result_counts.values())
    assert result_counts.get("publicly_accessible", 0) / total > 0.50  # ~60%
    assert result_counts.get("blocked_by_robots", 0) / total < 0.20  # ~15%
    assert result_counts.get("poorly_extractable", 0) / total < 0.20  # ~15%
    assert result_counts.get("http_error_4xx", 0) / total < 0.15  # ~10%


def test_generate_mock_website_checks_robots_allowed_distribution():
    """Test that robots_allowed follows expected distribution."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=200)

    true_count = sum(1 for check in checks if check["robots_allowed"])
    false_count = sum(1 for check in checks if not check["robots_allowed"])

    # Verify approximate 80/20 distribution (with tolerance adjusted for
    # blocked_by_robots forcing robots_allowed=False, which affects overall ratio)
    total = true_count + false_count
    assert true_count / total > 0.60  # ~80% but with some tolerance for blocked_by_robots
    assert false_count / total < 0.40  # ~20% plus blocked_by_robots


def test_generate_mock_website_checks_http_status_distribution():
    """Test that http_status follows expected distribution."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=200)

    status_counts = {}
    for check in checks:
        status = check["http_status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    # Verify all status codes are valid
    assert set(status_counts.keys()).issubset({200, 403, 404})


def test_generate_mock_website_checks_noindex_distribution():
    """Test that noindex follows expected distribution."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=200)

    true_count = sum(1 for check in checks if check["noindex"])
    false_count = sum(1 for check in checks if not check["noindex"])

    # Verify approximate 10/90 distribution (with tolerance)
    total = true_count + false_count
    assert true_count / total < 0.20  # ~10%
    assert false_count / total > 0.80  # ~90%


def test_generate_mock_website_checks_robots_allowed_consistency():
    """Test that blocked_by_robots results have robots_allowed=False."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=100)

    for check in checks:
        if check["result"] == "blocked_by_robots":
            assert check["robots_allowed"] is False, \
                "blocked_by_robots result should have robots_allowed=False"


def test_generate_mock_website_checks_realistic_timestamps():
    """Test that generated timestamps are within last 30 days."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=30)

    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)

    for check in checks:
        timestamp = datetime.fromisoformat(check["check_timestamp"])
        assert thirty_days_ago <= timestamp <= now


def test_generate_mock_website_checks_response_time_range():
    """Test that response times are in valid range."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=30)

    for check in checks:
        assert 10 <= check["response_time_ms"] <= 500


def test_generate_mock_website_checks_unique_ids():
    """Test that generated check IDs are unique."""
    engine = RandomMockEngine({})
    checks = engine.generate_mock_website_checks(count=100)

    ids = [check["id"] for check in checks]
    assert len(ids) == len(set(ids)), "Generated IDs are not unique"
