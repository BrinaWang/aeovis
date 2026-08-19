"""Engine construction from the provider registry."""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

from aeo_eval.config import PROVIDERS, config as app_config
from aeo_eval.engine.base import BaseEngine


def available_engines() -> List[str]:
    """Names of engines with a registered implementation."""
    return sorted(PROVIDERS)


def create_engine(name: str, config_dict: Optional[Dict[str, Any]] = None) -> BaseEngine:
    """Instantiate an engine by registry name.

    Args:
        name: Key in aeo_eval.config.PROVIDERS.
        config_dict: Engine configuration as a plain dict. Defaults to
            the matching provider section of the global config.

    Raises:
        ValueError: unknown name, or the engine rejects its config
            (e.g. a missing API key).
    """
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown engine '{name}'. Available: {', '.join(available_engines())}"
        )
    module_path, class_name = PROVIDERS[name].split(":")
    engine_cls = getattr(importlib.import_module(module_path), class_name)
    if config_dict is None:
        provider = app_config.providers.get(name)
        config_dict = provider.model_dump() if provider else {}
    return engine_cls(config_dict)
