"""Tests for source classification."""

from aeo_eval.citations.classifier import classify_source


def test_classify_striim_owned():
    """Test Striim-owned classification."""
    assert classify_source("https://striim.com/docs", "striim.com") == "striim_owned"


def test_classify_competitor():
    """Test competitor classification."""
    assert classify_source("https://fivetran.com/blog", "fivetran.com") == "competitor"


def test_classify_other():
    """Test default classification."""
    assert classify_source("https://example.com/", "example.com") == "other"


def test_classify_technical_publication():
    """Test technical publication classification."""
    assert classify_source("https://github.com/user/repo", "github.com") == "technical_publication"
