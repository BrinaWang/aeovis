from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal, Dict, Any


@dataclass
class RunResult:
    """Result from running a single prompt through an answer engine."""
    run_id: str
    run_batch_id: str  # Groups results from same evaluation batch
    prompt_id: str
    engine: str
    model: str
    status: str  # "success", "failed", "rate_limited", "timeout"
    response_text: Optional[str]
    error: Optional[str]
    latency_ms: Optional[int]
    estimated_cost: Optional[float] = None  # Deprecated; use actual_cost

    # NEW: Token tracking for cost calculation
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    actual_cost: Optional[float] = None  # Calculated from tokens

    # NEW: Execution metadata
    engine_name: str = ""  # Engine class name
    run_timestamp: Optional[datetime] = None  # When this was executed
    run_type: Literal["manual", "scheduled", "dashboard"] = "manual"  # How was it triggered

    def total_tokens(self) -> Optional[int]:
        """Calculate total tokens used."""
        if self.input_tokens is not None and self.output_tokens is not None:
            return self.input_tokens + self.output_tokens
        return None


@dataclass
class EvaluationRun:
    """Summary of a complete evaluation run (batch of prompts)."""
    run_id: str
    run_timestamp: datetime
    engine: str
    model_version: str
    prompts_run: int  # Total prompts attempted
    prompts_succeeded: int  # Successful runs
    prompts_failed: int  # Failed runs
    total_cost: float  # Total spend for this run
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    run_type: Literal["manual", "scheduled", "dashboard"] = "manual"
    filters_applied: Dict[str, Any] = field(default_factory=dict)  # topic, persona filters used
    run_notes: str = ""  # Why this run was triggered
    duration_seconds: float = 0.0  # Total execution time

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.prompts_run == 0:
            return 0.0
        return (self.prompts_succeeded / self.prompts_run) * 100

    @property
    def average_cost_per_prompt(self) -> float:
        """Calculate average cost per prompt."""
        if self.prompts_succeeded == 0:
            return 0.0
        return self.total_cost / self.prompts_succeeded
