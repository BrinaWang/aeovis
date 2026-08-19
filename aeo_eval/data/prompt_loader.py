from __future__ import annotations

import json
from pathlib import Path
from typing import List

from aeo_eval.models.prompt import Prompt


def load_prompts(path: str | Path) -> List[Prompt]:
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
