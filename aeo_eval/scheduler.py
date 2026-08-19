"""Job scheduling for periodic evaluation runs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


@dataclass
class ScheduledRunConfig:
    """Configuration for a scheduled evaluation run."""

    job_id: str
    name: str
    engine: str
    cron_expression: str
    topic: Optional[str] = None
    persona: Optional[str] = None
    created_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    is_active: bool = True
    notes: str = ""


class ScheduleManager:
    """Manages scheduled evaluation runs using APScheduler."""

    def __init__(self):
        """Initialize the schedule manager."""
        self.scheduler = BackgroundScheduler()
        self.scheduled_runs: dict[str, ScheduledRunConfig] = {}

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    def add_scheduled_run(
        self,
        name: str,
        engine: str,
        cron_expression: str,
        topic: Optional[str] = None,
        persona: Optional[str] = None,
        notes: str = "",
    ) -> str:
        """
        Add a new scheduled evaluation run.

        Args:
            name: Human-readable name for the run
            engine: Engine to use (claude, openai, etc.)
            cron_expression: Cron expression (e.g., "0 9 * * MON")
            topic: Optional topic filter
            persona: Optional persona filter
            notes: Optional notes

        Returns:
            Job ID of the created scheduled run
        """
        job_id = str(uuid4())

        # Create scheduled run config
        config = ScheduledRunConfig(
            job_id=job_id,
            name=name,
            engine=engine,
            cron_expression=cron_expression,
            topic=topic,
            persona=persona,
            created_at=datetime.now(),
            is_active=True,
            notes=notes,
        )

        # Store configuration
        self.scheduled_runs[job_id] = config

        # Add job to scheduler
        try:
            self.scheduler.add_job(
                self._run_scheduled_job,
                trigger=CronTrigger.from_crontab(cron_expression),
                id=job_id,
                name=name,
                args=[job_id],
                misfire_grace_time=60,
                coalesce=True,
            )
            logger.info(f"Scheduled run added: {name} (ID: {job_id})")
            return job_id
        except Exception as e:
            logger.error(f"Failed to add scheduled run: {e}")
            del self.scheduled_runs[job_id]
            raise

    def list_scheduled_runs(self) -> List[ScheduledRunConfig]:
        """Get list of all scheduled runs."""
        return list(self.scheduled_runs.values())

    def get_scheduled_run(self, job_id: str) -> Optional[ScheduledRunConfig]:
        """Get a specific scheduled run by ID."""
        return self.scheduled_runs.get(job_id)

    def pause_scheduled_run(self, job_id: str) -> None:
        """Pause a scheduled run."""
        if job_id not in self.scheduled_runs:
            raise ValueError(f"Unknown job ID: {job_id}")

        config = self.scheduled_runs[job_id]
        config.is_active = False
        self.scheduler.pause_job(job_id)
        logger.info(f"Scheduled run paused: {config.name}")

    def resume_scheduled_run(self, job_id: str) -> None:
        """Resume a paused scheduled run."""
        if job_id not in self.scheduled_runs:
            raise ValueError(f"Unknown job ID: {job_id}")

        config = self.scheduled_runs[job_id]
        config.is_active = True
        self.scheduler.resume_job(job_id)
        logger.info(f"Scheduled run resumed: {config.name}")

    def delete_scheduled_run(self, job_id: str) -> None:
        """Delete a scheduled run."""
        if job_id not in self.scheduled_runs:
            raise ValueError(f"Unknown job ID: {job_id}")

        config = self.scheduled_runs[job_id]
        self.scheduler.remove_job(job_id)
        del self.scheduled_runs[job_id]
        logger.info(f"Scheduled run deleted: {config.name}")

    def trigger_now(self, job_id: str) -> None:
        """Manually trigger a scheduled run immediately."""
        if job_id not in self.scheduled_runs:
            raise ValueError(f"Unknown job ID: {job_id}")

        config = self.scheduled_runs[job_id]
        logger.info(f"Triggering scheduled run: {config.name}")
        self._run_scheduled_job(job_id)

    def _run_scheduled_job(self, job_id: str) -> None:
        """Execute a scheduled job."""
        config = self.scheduled_runs[job_id]

        if not config.is_active:
            logger.warning(f"Job is paused, skipping: {config.name}")
            return

        logger.info(f"Running scheduled job: {config.name} (engine: {config.engine})")

        # Import here to avoid circular dependency
        from aeo_eval.cli import cmd_run
        import argparse

        # Create arguments for cmd_run
        args = argparse.Namespace(
            engine=config.engine,
            questions=None,
            limit=None,
            topic=config.topic,
            persona=config.persona,
            priority=None,
            cost_limit=None,
            dry_run=False,
            notes=f"Scheduled run: {config.name}",
            db=None,
            verbose=False,
            log_level="INFO",
        )

        try:
            cmd_run(args)
            config.last_run_at = datetime.now()
            logger.info(f"Scheduled job completed: {config.name}")
        except Exception as e:
            logger.error(f"Scheduled job failed: {config.name}: {e}")

    def get_next_run_times(self, job_id: str, count: int = 5) -> List[datetime]:
        """Get next scheduled run times for a job."""
        job = self.scheduler.get_job(job_id)
        if not job:
            return []

        next_runs = []
        next_time = job.next_run_time

        # APScheduler provides next_run_time directly
        if next_time:
            next_runs.append(next_time)

        return next_runs

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
