"""Canonical database path resolution."""
from aeo_eval.config import config as app_config
from aeo_eval.engine.mock_engine import MockEngine
from aeo_eval.orchestrator import AEOPipelineOrchestrator


def test_orchestrator_defaults_to_config_db_path():
    orch = AEOPipelineOrchestrator(MockEngine(), config={})
    assert orch.db_path == str(app_config.general.output_db_path)


def test_orchestrator_explicit_db_path_wins(tmp_path):
    db = tmp_path / "explicit.db"
    orch = AEOPipelineOrchestrator(MockEngine(), config={"db_path": str(db)})
    assert orch.db_path == str(db)
