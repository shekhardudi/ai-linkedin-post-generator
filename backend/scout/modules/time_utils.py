"""Time range utilities for Pulse Scout module scanners."""

from datetime import datetime, timedelta, timezone


def days_to_cutoff(days: int) -> datetime:
    """Return a UTC-aware datetime representing `days` ago from now.

    Always timezone-aware (UTC) so it can be safely compared with
    arxiv paper.published datetimes, which are also UTC-aware.
    """
    return datetime.now(timezone.utc) - timedelta(days=days)
