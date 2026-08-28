#!/usr/bin/env python3
"""Migration script to add run_id to crawler_logs and website_checks tables."""

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "eval_runs.db"


def backup_database():
    """Create a backup of the database."""
    import shutil
    backup_path = DB_PATH.with_suffix('.db.backup')
    shutil.copy2(DB_PATH, backup_path)
    print(f"✓ Database backed up to {backup_path}")
    return backup_path


def migrate_database():
    """Add run_id columns to crawler_logs and website_checks tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        # Check if run_id column already exists in crawler_logs
        cursor.execute("PRAGMA table_info(crawler_logs)")
        columns = [row[1] for row in cursor.fetchall()]

        if "run_id" not in columns:
            print("Adding run_id column to crawler_logs...")
            # Add run_id column (nullable for now, we'll handle old data)
            cursor.execute("ALTER TABLE crawler_logs ADD COLUMN run_id TEXT")
            print("✓ Added run_id to crawler_logs")
        else:
            print("ℹ run_id column already exists in crawler_logs")

        # Check if run_id column already exists in website_checks
        cursor.execute("PRAGMA table_info(website_checks)")
        columns = [row[1] for row in cursor.fetchall()]

        if "run_id" not in columns:
            print("Adding run_id column to website_checks...")
            # Add run_id column (nullable for now, we'll handle old data)
            cursor.execute("ALTER TABLE website_checks ADD COLUMN run_id TEXT")
            print("✓ Added run_id to website_checks")
        else:
            print("ℹ run_id column already exists in website_checks")

        # Delete old mock_generator data (it has no run_id and is contaminated)
        print("\nCleaning up old mock_generator data (no run_id reference)...")
        cursor.execute("DELETE FROM crawler_logs WHERE run_id IS NULL")
        deleted_logs = cursor.rowcount

        cursor.execute("DELETE FROM website_checks WHERE run_id IS NULL")
        deleted_checks = cursor.rowcount

        print(f"✓ Deleted {deleted_logs} old crawler_log records")
        print(f"✓ Deleted {deleted_checks} old website_check records")

        conn.commit()
        print("\n✓ Migration completed successfully!")
        return True

    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"✗ Database not found at {DB_PATH}")
        sys.exit(1)

    print(f"Migrating database at {DB_PATH}")
    print("-" * 50)

    # Backup first
    backup_database()
    print()

    # Run migration
    success = migrate_database()

    sys.exit(0 if success else 1)
