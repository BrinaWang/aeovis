"""Command-line interface for the AEO Visibility Platform."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from aeo_eval.config import config
from aeo_eval.data.prompt_loader import load_prompts
from aeo_eval.engine.factory import available_engines, create_engine
from aeo_eval.orchestrator import AEOPipelineOrchestrator
from aeo_eval.runner.evaluator import RunOptions
from aeo_eval.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Set up logging configuration."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_run(args) -> None:
    """Execute a full evaluation run: engine -> analysis -> metrics ->
    citations -> gaps -> recommendations -> auto-approval."""
    setup_logging(level=args.log_level)

    # Load prompts
    questions_path = args.questions or str(config.general.question_json_path)
    prompts = load_prompts(questions_path)
    if args.limit:
        prompts = prompts[: args.limit]

    # Initialize engine
    try:
        engine = create_engine(args.engine)
    except (ValueError, ImportError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Prepare run options
    run_options = RunOptions(
        topic=args.topic,
        persona=args.persona,
        priority=args.priority,
        dry_run=args.dry_run,
        run_type="manual",
        notes=args.notes or "",
    )

    # The orchestrator is the top-level pipeline entry point: it drives the
    # Evaluator (answer engine + Module 3 analysis extraction) and then
    # runs Modules 4/5/8/9 (metrics, citations, gaps, recommendations,
    # auto-approval) and persists everything.
    db_path = args.db or str(config.general.output_db_path)
    pipeline_config = {
        "db_path": db_path,
        "cost_limit_per_run": args.cost_limit or config.general.cost_limit_per_run,
    }
    orchestrator = AEOPipelineOrchestrator(engine, pipeline_config)

    try:
        result = orchestrator.run_full_pipeline(prompts, run_options)

        # Print summary
        print("\n" + "=" * 70)
        print(f"Pipeline Run Summary")
        print("=" * 70)
        print(f"Run ID:              {result['run_id']}")
        print(f"Prompts:             {result['num_prompts']}")
        print(f"Gaps detected:       {result['num_gaps']}")
        print(f"Recommendations:     {result['num_recommendations']}")
        print(f"Auto-approved:       {result['num_auto_approved']}")

        if run_options.topic:
            print(f"Topic filter:        {run_options.topic}")
        if run_options.persona:
            print(f"Persona filter:      {run_options.persona}")
        if not args.dry_run:
            print(f"Database:            {db_path}")

        print("=" * 70 + "\n")

    except KeyboardInterrupt:
        print("\nRun cancelled by user.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_history(args) -> None:
    """Show history of past runs."""
    setup_logging(level=args.log_level)

    db_path = args.db or str(config.general.output_db_path)
    store = SQLiteStore(db_path)

    # For now, just list runs from SQLite
    print(f"Reading history from {db_path}")
    print("(History query not yet implemented - check {db_path} directly)")


def cmd_schedule(args) -> None:
    """Manage scheduled runs."""
    setup_logging(level=args.log_level)

    if args.list:
        print("Scheduled runs:")
        print("(Scheduling not yet implemented)")
    elif args.add:
        print(f"Adding scheduled run: {args.add}")
        print("(Scheduling not yet implemented)")
    elif args.trigger:
        print(f"Triggering scheduled run: {args.trigger}")
        print("(Scheduling not yet implemented)")
    else:
        print("Use --list, --add, or --trigger with schedule command")


def cmd_report(args) -> None:
    """Display demo report for a run."""
    from aeo_eval.demo.report import print_run_summary

    db_path = args.db or str(config.general.output_db_path)
    run_id = args.run_id

    print_run_summary(db_path, run_id)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AEO Visibility Platform - Answer Engine Evaluation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 5 prompts with Claude engine
  python -m aeo_eval.cli run --engine claude --limit 5

  # Run prompts for a specific topic
  python -m aeo_eval.cli run --engine claude --topic "Oracle CDC"

  # Estimate cost without running (dry-run)
  python -m aeo_eval.cli run --engine claude --dry-run

  # Show past runs
  python -m aeo_eval.cli history

  # Schedule a monthly run
  python -m aeo_eval.cli schedule --add "monthly-oracle" --cron "0 9 * * MON"
        """,
    )

    # Global options
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # RUN command
    run_parser = subparsers.add_parser("run", help="Run evaluation prompts")
    run_parser.add_argument(
        "--engine",
        choices=available_engines(),
        default="claude",
        help="AI engine to use",
    )
    run_parser.add_argument(
        "--questions",
        type=str,
        default=None,
        help="Path to question JSON file",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum prompts to run",
    )
    run_parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Filter to specific topic",
    )
    run_parser.add_argument(
        "--persona",
        type=str,
        default=None,
        help="Filter to specific persona",
    )
    run_parser.add_argument(
        "--priority",
        type=str,
        choices=["High", "Medium", "Low"],
        default=None,
        help="Filter to specific priority",
    )
    run_parser.add_argument(
        "--cost-limit",
        type=float,
        default=None,
        help="Cost limit for this run (dollars)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate cost without running",
    )
    run_parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Notes for this run",
    )
    run_parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="SQLite database path",
    )
    run_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    run_parser.set_defaults(func=cmd_run)

    # HISTORY command
    history_parser = subparsers.add_parser("history", help="Show run history")
    history_parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="SQLite database path",
    )
    history_parser.set_defaults(func=cmd_history)

    # SCHEDULE command
    schedule_parser = subparsers.add_parser("schedule", help="Manage scheduled runs")
    schedule_group = schedule_parser.add_mutually_exclusive_group()
    schedule_group.add_argument(
        "--list",
        action="store_true",
        help="List scheduled runs",
    )
    schedule_group.add_argument(
        "--add",
        type=str,
        metavar="NAME",
        help="Add new scheduled run",
    )
    schedule_group.add_argument(
        "--trigger",
        type=str,
        metavar="JOB_ID",
        help="Trigger a scheduled run now",
    )
    schedule_parser.add_argument(
        "--cron",
        type=str,
        help="Cron expression (e.g., '0 9 * * MON')",
    )
    schedule_parser.set_defaults(func=cmd_schedule)

    # REPORT command
    report_parser = subparsers.add_parser("report", help="Display evaluation report")
    report_parser.add_argument("run_id", help="Run ID to report on")
    report_parser.add_argument("--db", help="Database path")
    report_parser.set_defaults(func=cmd_report)

    # Parse and execute
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
