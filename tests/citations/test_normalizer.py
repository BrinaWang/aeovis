"""Tests for URL normalization."""

from aeo_eval.citations.normalizer import normalize_url, extract_domain


def test_normalize_url():
    """Test URL normalization."""
    assert normalize_url("https://example.com/path?query=1#frag") == "https://example.com/path"
    assert normalize_url("https://EXAMPLE.COM/path/") == "https://example.com/path"


def test_extract_domain():
    """Test domain extraction."""
    assert extract_domain("https://example.com/path") == "example.com"
    assert extract_domain("https://sub.example.com/path") == "sub.example.com"


def test_normalize_empty_url():
    """Test empty URL handling."""
    assert normalize_url("") == ""
