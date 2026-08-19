"""Shared test fixtures."""
import pytest


@pytest.fixture(autouse=True)
def isolate_db_path(monkeypatch, tmp_path):
    """Point the configured output DB at a per-test temp file.

    Any code path that falls back to config.general.output_db_path must
    never touch the real data/ directory during tests.
    """
    from aeo_eval.config import config as app_config

    monkeypatch.setattr(app_config.general, "output_db_path", tmp_path / "test.db")
    monkeypatch.setattr(app_config.providers["claude"], "api_key", None, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
