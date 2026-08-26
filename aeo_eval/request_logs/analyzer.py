"""Request log analyzer for normalizing parsed logs into crawler_logs schema."""
import logging
from typing import Dict, List, Optional
from .classifier import CrawlerClassifier

logger = logging.getLogger(__name__)


class RequestLogAnalyzer:
    """Analyze parsed request logs and normalize to crawler_logs schema.

    Takes output from RequestLogParser, classifies crawlers using
    CrawlerClassifier, and produces records ready for database insertion.
    """

    def __init__(self):
        """Initialize analyzer with crawler classifier."""
        self.classifier = CrawlerClassifier()

    def analyze(self, records: List[Dict]) -> List[Dict]:
        """Analyze request log records and normalize to crawler_logs schema.

        Args:
            records: List of parsed request records from RequestLogParser.
                     Expected fields: id, timestamp, host, path, status_code,
                     user_agent, response_time_ms, normalized_path.

        Returns:
            List of normalized records ready for crawler_logs table insertion.
            Fields: id, timestamp, host, path, crawler, http_status,
                    response_time_ms, edge_action, log_source, ua_classification.
        """
        normalized = []
        for record in records:
            normalized_record = self._normalize_record(record)
            if normalized_record:
                normalized.append(normalized_record)
        return normalized

    def _normalize_record(self, record: Dict) -> Optional[Dict]:
        """Normalize a single parsed record to crawler_logs schema.

        Args:
            record: A parsed request record.

        Returns:
            A normalized record dict, or None if normalization fails.
        """
        try:
            user_agent = record.get("user_agent", "")
            status_code = record.get("status_code")

            # Classify the user agent
            ua_classification = self.classifier.classify(user_agent)

            # Determine the crawler name from classification
            crawler = None
            if ua_classification.get("class") == "known_ai_crawler":
                # Extract crawler name from matched pattern
                crawler = ua_classification.get("matched_pattern", "unknown")
            elif ua_classification.get("class") == "delegated_agent":
                crawler = ua_classification.get("tool_name", "unknown")
            elif ua_classification.get("class") == "search_crawler":
                crawler = ua_classification.get("matched_pattern", "unknown")
            else:
                # For other classifications, use a generic name or None
                crawler = None

            # Determine edge action based on status code
            edge_action = self._classify_edge_action(status_code)

            # Build normalized record
            normalized = {
                "id": record.get("id"),
                "timestamp": record.get("timestamp"),
                "host": record.get("host"),
                "path": record.get("normalized_path") or record.get("path"),
                "crawler": crawler,
                "http_status": status_code,
                "response_time_ms": record.get("response_time_ms"),
                "edge_action": edge_action,
                "log_source": "request_log",
                "ua_classification": ua_classification,
            }

            return normalized

        except Exception as e:
            logger.warning(f"Failed to normalize record: {e}")
            return None

    def _classify_edge_action(self, status_code: Optional[int]) -> Optional[str]:
        """Classify edge action based on HTTP status code.

        Args:
            status_code: The HTTP status code.

        Returns:
            One of "allowed", "blocked", "rate_limited", "error", or None.
        """
        if status_code is None:
            return None

        if 200 <= status_code < 300:
            return "allowed"
        elif status_code == 403:
            return "blocked"
        elif status_code == 429:
            return "rate_limited"
        elif status_code >= 400:
            return "error"
        else:
            return None

    def summarize_activity(self, records: List[Dict]) -> Dict:
        """Summarize crawler activity statistics (optional helper).

        Args:
            records: List of normalized records.

        Returns:
            Dictionary with activity summary stats.
        """
        summary = {
            "total_records": len(records),
            "by_crawler": {},
            "by_edge_action": {},
            "by_status_code": {},
        }

        for record in records:
            # Count by crawler
            crawler = record.get("crawler")
            if crawler:
                summary["by_crawler"][crawler] = summary["by_crawler"].get(crawler, 0) + 1

            # Count by edge action
            action = record.get("edge_action")
            if action:
                summary["by_edge_action"][action] = (
                    summary["by_edge_action"].get(action, 0) + 1
                )

            # Count by status code
            status = record.get("http_status")
            if status:
                status_str = str(status)
                summary["by_status_code"][status_str] = (
                    summary["by_status_code"].get(status_str, 0) + 1
                )

        return summary
