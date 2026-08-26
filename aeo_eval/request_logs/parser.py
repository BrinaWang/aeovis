"""Request log parser for ingesting and normalizing JSONL request logs."""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
import uuid

logger = logging.getLogger(__name__)


class RequestLogParser:
    """Parser for JSONL-formatted request logs.

    Validates required fields, normalizes paths, and filters by date.
    """

    REQUIRED_FIELDS = {"timestamp", "host", "path", "status_code", "user_agent"}

    def parse_json_line(self, line: str) -> Optional[Dict]:
        """Parse a single JSONL record and validate required fields.

        Args:
            line: A single JSON line from the log file.

        Returns:
            A normalized dict with request data, or None if validation fails.
        """
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON line: {e}")
            return None

        # Validate required fields are present
        missing_fields = self.REQUIRED_FIELDS - set(data.keys())
        if missing_fields:
            logger.warning(
                f"Record missing required fields {missing_fields}: {line[:100]}"
            )
            return None

        # Build normalized record
        normalized_path = self._normalize_path(data.get("path", ""))
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": data.get("timestamp"),
            "host": data.get("host"),
            "path": data.get("path"),
            "status_code": data.get("status_code"),
            "user_agent": data.get("user_agent"),
            "response_time_ms": data.get("response_time_ms"),
            "referrer": data.get("referrer"),
            "normalized_path": normalized_path,
        }

        return record

    def parse_file(
        self, file_path: str, days_back: int = 90
    ) -> List[Dict]:
        """Parse a JSONL file, filtering by date and skipping malformed records.

        Args:
            file_path: Path to the JSONL log file.
            days_back: Number of days to look back from today (default 90).

        Returns:
            List of normalized request records within the date range.
        """
        records = []
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            logger.warning(f"Log file not found: {file_path}")
            return records

        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        try:
            with open(file_path_obj, "r") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    parsed = self.parse_json_line(line)
                    if parsed is None:
                        continue

                    # Filter by date
                    try:
                        record_date = datetime.fromisoformat(
                            parsed["timestamp"].replace("Z", "+00:00")
                        )
                        if record_date < cutoff_date:
                            continue
                    except (ValueError, AttributeError) as e:
                        logger.warning(
                            f"Line {line_num}: Invalid timestamp format: {e}"
                        )
                        continue

                    records.append(parsed)

        except IOError as e:
            logger.error(f"Failed to read log file {file_path}: {e}")

        return records

    def _normalize_path(self, path: str) -> str:
        """Remove query parameters from a URL path.

        Args:
            path: The URL path to normalize.

        Returns:
            The path with query parameters removed.
        """
        if not path:
            return ""

        parsed = urlparse(path)
        return parsed.path if parsed.path else "/"
