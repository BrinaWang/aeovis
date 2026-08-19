"""Engine factory tests."""
import argparse

import pytest

from aeo_eval import cli as cli_module
from aeo_eval.engine.factory import available_engines, create_engine
from aeo_eval.engine.mock_engine import MockEngine


def test_available_engines_only_lists_registered():
    engines = available_engines()
    assert "mock" in engines
    assert "claude" in engines
    assert "openai" in engines
    assert "gemini" not in engines  # config-only, no implementation
    assert "grok" not in engines


def test_create_engine_mock():
    assert isinstance(create_engine("mock"), MockEngine)


def test_create_engine_unknown_name():
    with pytest.raises(ValueError, match="Unknown engine 'grok'"):
        create_engine("grok")


def test_create_engine_hands_engines_a_plain_dict():
    # Regression: the CLI used to pass a ProviderConfig object, which
    # crashed ClaudeEngine with AttributeError on .get().
    engine = create_engine("claude", {"api_key": "test-key"})
    assert engine.config["api_key"] == "test-key"


def test_cmd_run_exits_gracefully_when_engine_import_fails(monkeypatch, capsys):
    # Regression: an engine module (e.g. openai_engine.py) can raise
    # ImportError at construction time if its SDK isn't installed. cmd_run
    # must print a friendly message and exit(1), not let the raw traceback
    # propagate, so it must catch ImportError alongside ValueError.
    monkeypatch.setattr(cli_module, "load_prompts", lambda path: [{"id": "p1"}])

    def fake_create_engine(name):
        raise ImportError("Install openai SDK.")

    monkeypatch.setattr(cli_module, "create_engine", fake_create_engine)

    args = argparse.Namespace(
        log_level="INFO",
        questions=None,
        limit=1,
        engine="openai",
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_module.cmd_run(args)

    assert exc_info.value.code == 1
    assert "Install openai SDK." in capsys.readouterr().err
