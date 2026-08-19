from .sqlite_store import SQLiteStore

__all__ = [
    "SQLiteStore",
]

# Export main methods for convenience
def save_analysis(*args, **kwargs):
    """Save a single response analysis result."""
    return SQLiteStore.save_analysis(*args, **kwargs)


def save_batch_analyses(*args, **kwargs):
    """Save multiple response analyses in a transaction."""
    return SQLiteStore.save_batch_analyses(*args, **kwargs)


def get_raw_responses_by_batch(*args, **kwargs):
    """Fetch raw responses for a batch."""
    return SQLiteStore.get_raw_responses_by_batch(*args, **kwargs)


def get_analysis_by_batch(*args, **kwargs):
    """Fetch response analyses for a batch."""
    return SQLiteStore.get_analysis_by_batch(*args, **kwargs)


def get_batch_metadata(*args, **kwargs):
    """Fetch batch metadata."""
    return SQLiteStore.get_batch_metadata(*args, **kwargs)
