"""Load the buyer-question dataset (``question.json``) into Prompt objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from aeo_eval.models.prompt import Prompt


def load_prompts(path: str | Path) -> List[Prompt]:
    """Read a question dataset file and return its enabled prompts.

    The file is a JSON object with a ``metadata`` block and a
    ``questions`` array. Each question needs ``id``, ``prompt``, ``topic``,
    ``persona``, ``intent`` and ``priority``; ``enabled`` (default False
    here, so a question must opt in explicitly), ``variant_of`` and
    ``tags`` are optional. Disabled questions are dropped at load time,
    so every downstream ``Prompt`` has ``enabled=True``. Order is
    preserved, which matters because the CLI/dashboard ``--limit`` is a
    plain prefix slice of this list.
    """
    data = json.loads(Path(path).read_text())
    prompts: List[Prompt] = []

    for item in data.get("questions", []):
        if not item.get("enabled", False):
            continue

        prompts.append(
            Prompt(
                id=item["id"],
                prompt=item["prompt"],
                topic=item["topic"],
                persona=item["persona"],
                intent=item["intent"],
                priority=item["priority"],
                enabled=item.get("enabled", True),
                variant_of=item.get("variant_of"),
                tags=item.get("tags", []),
            )
        )

    return prompts
