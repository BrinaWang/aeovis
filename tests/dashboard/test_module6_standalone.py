"""Standalone Module 6 runs from the dashboard must persist their checks."""
import sqlite3

from aeo_eval.config import config as app_config
from aeo_eval.dashboard import app as dashboard_app


def _fake_check_pages(self, pages, crawlers):
    return [{
        "id": "chk-1",
        "striim_url": pages[0],
        "crawler": crawlers[0],
        "robots_allowed": 1,
        "in_sitemap": None,
        "http_status": 200,
        "response_time_ms": 12,
        "noindex": 0,
        "canonical_url": None,
        "result": "publicly_accessible",
        "check_timestamp": "2026-09-16T00:00:00Z",
    }]


def test_standalone_module6_run_stores_checks(monkeypatch):
    monkeypatch.setattr(
        dashboard_app.WebsiteAccessibilityChecker, "check_pages", _fake_check_pages
    )

    result = dashboard_app.run_module6_standalone(
        ["https://www.striim.com/product/"], ["GPTBot"]
    )

    assert result["success"] is True, result
    conn = sqlite3.connect(str(app_config.general.output_db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM website_checks WHERE run_id = ?", (result["run_id"],)
    ).fetchone()[0]
    assert count == 1
