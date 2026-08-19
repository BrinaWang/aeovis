from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Prompt:
    id: str
    prompt: str
    topic: str
    persona: str
    intent: str
    priority: str
    enabled: bool = True
    variant_of: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class Citation:
    url: str
    normalized_url: Optional[str] = None
    domain: Optional[str] = None


@dataclass
class EngineResponse:
    prompt_id: str
    engine: str
    model: str
    raw_response: str
    citations: List[Citation] = field(default_factory=list)
    latency_ms: int = 0
    estimated_cost: float = 0.0
    status: str = "success"
    error: Optional[str] = None


@dataclass
class ExtractionResult:
    prompt_id: str
    striim_mentioned: bool = False
    striim_recommended: bool = False
    competitors: List[str] = field(default_factory=list)
    striim_position: Optional[int] = None
    confidence: float = 0.0
