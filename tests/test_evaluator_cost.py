"""Tests for evaluator cost tracking."""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from aeo_eval.runner.evaluator import (
    Evaluator,
    CostTracker,
    RunOptions,
    CostLimitExceeded,
)
from aeo_eval.models.prompt import Prompt
from aeo_eval.models.result import RunResult
from aeo_eval.engine.mock_engine import MockEngine


class TestCostTracker:
    """Test cost tracking."""

    def test_cost_tracker_initialization(self):
        """Test cost tracker initialization."""
        tracker = CostTracker(limit_dollars=35.0)
        assert tracker.limit == 35.0
        assert tracker.spent == 0.0
        assert tracker.remaining() == 35.0

    def test_add_cost(self):
        """Test adding costs."""
        tracker = CostTracker(limit_dollars=10.0)

        tracker.add("prompt-1", 2.5)
        assert tracker.spent == 2.5
        assert tracker.remaining() == 7.5

        tracker.add("prompt-2", 3.0)
        assert tracker.spent == 5.5
        assert tracker.remaining() == 4.5

    def test_cost_limit_exceeded(self):
        """Test cost limit enforcement."""
        tracker = CostTracker(limit_dollars=10.0)

        tracker.add("prompt-1", 6.0)
        assert tracker.spent == 6.0

        # This should exceed limit
        with pytest.raises(CostLimitExceeded):
            tracker.add("prompt-2", 5.0)

    def test_cost_summary(self):
        """Test cost summary string."""
        tracker = CostTracker(limit_dollars=10.0)
        tracker.add("prompt-1", 3.0)

        summary = tracker.summary()
        assert "3.00" in summary
        assert "10.00" in summary

    def test_cost_breakdown(self):
        """Test cost breakdown by prompt."""
        tracker = CostTracker(limit_dollars=100.0)

        tracker.add("prompt-1", 2.0)
        tracker.add("prompt-2", 3.0)
        tracker.add("prompt-1", 1.0)  # Add to same prompt

        breakdown = tracker.breakdown()
        assert breakdown["prompt-1"] == 3.0
        assert breakdown["prompt-2"] == 3.0


class TestEvaluatorCostTracking:
    """Test evaluator cost tracking."""

    def test_evaluator_initialization(self):
        """Test evaluator initialization."""
        engine = MockEngine()
        evaluator = Evaluator(engine, config={"cost_limit_per_run": 50.0})

        assert evaluator.engine == engine
        assert evaluator.cost_tracker.limit == 50.0

    def test_run_one_with_cost_tracking(self):
        """Test running a single prompt with cost tracking."""
        engine = MockEngine()
        evaluator = Evaluator(engine)

        prompt = Prompt(
            id="test-1",
            prompt="What is 2+2?",
            topic="Math",
            persona="Student",
            intent="Educational",
            priority="High",
            enabled=True,
        )

        result = evaluator.run_one(prompt)

        assert result.prompt_id == "test-1"
        assert result.status == "success"
        assert result.actual_cost is not None or result.estimated_cost is not None

    def test_run_one_respects_cost_limit(self):
        """Test that cost limit is respected."""
        engine = Mock()
        engine.name = "test-engine"
        engine.model_name = "test-model"
        engine.estimate_cost = Mock(return_value=100.0)

        evaluator = Evaluator(engine, config={"cost_limit_per_run": 50.0})

        prompt = Prompt(
            id="test-1",
            prompt="Question?",
            topic="Test",
            persona="Test",
            intent="Test",
            priority="High",
            enabled=True,
        )

        # Cost estimate exceeds limit
        with pytest.raises(CostLimitExceeded):
            evaluator.run_one(prompt, options=RunOptions(dry_run=False))

    def test_dry_run_no_api_call(self):
        """Test that dry-run doesn't call the engine."""
        engine = Mock()
        engine.name = "test-engine"
        engine.model_name = "test-model"
        engine.estimate_cost = Mock(return_value=5.0)

        evaluator = Evaluator(engine)

        prompt = Prompt(
            id="test-1",
            prompt="Question?",
            topic="Test",
            persona="Test",
            intent="Test",
            priority="High",
            enabled=True,
        )

        result = evaluator.run_one(prompt, options=RunOptions(dry_run=True))

        assert result.status == "dry_run"
        engine.run.assert_not_called()  # Should not call engine

    def test_run_batch_cost_tracking(self):
        """Test batch run cost tracking."""
        engine = MockEngine()
        evaluator = Evaluator(engine, config={"cost_limit_per_run": 100.0})

        prompts = [
            Prompt(
                id=f"test-{i}",
                prompt=f"Question {i}?",
                topic="Test",
                persona="Test",
                intent="Test",
                priority="High",
                enabled=True,
            )
            for i in range(3)
        ]

        results, summary = evaluator.run_batch(prompts)

        assert summary.prompts_run == 3
        assert summary.prompts_succeeded >= 1
        assert summary.total_cost >= 0

    def test_run_batch_with_filtering(self):
        """Test batch run with topic filtering."""
        engine = MockEngine()
        evaluator = Evaluator(engine)

        prompts = [
            Prompt(
                id="math-1",
                prompt="2+2?",
                topic="Math",
                persona="Student",
                intent="Educational",
                priority="High",
                enabled=True,
            ),
            Prompt(
                id="science-1",
                prompt="Newton?",
                topic="Science",
                persona="Student",
                intent="Educational",
                priority="High",
                enabled=True,
            ),
        ]

        # Filter to Math topic only
        results, summary = evaluator.run_batch(
            prompts,
            options=RunOptions(topic="Math"),
        )

        # Should only run 1 prompt
        assert summary.prompts_run == 1
        assert all(r.prompt_id == "math-1" for r in results)

    def test_run_batch_dry_run_estimate(self):
        """Test batch dry-run cost estimation."""
        engine = MockEngine()
        evaluator = Evaluator(engine, config={"cost_limit_per_run": 100.0})

        prompts = [
            Prompt(
                id=f"test-{i}",
                prompt=f"Question {i}?",
                topic="Test",
                persona="Test",
                intent="Test",
                priority="High",
                enabled=True,
            )
            for i in range(3)
        ]

        results, summary = evaluator.run_batch(
            prompts,
            options=RunOptions(dry_run=True),
        )

        assert all(r.status == "dry_run" for r in results)
        # Should have estimated costs even in dry-run
        assert summary.total_cost >= 0

    def test_evaluation_run_summary(self):
        """Test evaluation run summary generation."""
        engine = MockEngine()
        evaluator = Evaluator(engine)

        prompts = [
            Prompt(
                id="test-1",
                prompt="Q1?",
                topic="Test",
                persona="Test",
                intent="Test",
                priority="High",
                enabled=True,
            ),
        ]

        results, summary = evaluator.run_batch(prompts)

        assert summary.engine == engine.name
        assert summary.model_version == engine.model_name
        assert summary.success_rate >= 0
        assert summary.average_cost_per_prompt >= 0
        assert isinstance(summary.run_timestamp, datetime)
