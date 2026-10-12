"""Data retention: deletes old conversation logs, escalations, and rate-limit rows.

Runs inside the API (at startup, then every 24 hours) and can be run by hand:

    python -m app.retention
"""

import logging
import sys
import threading
from datetime import UTC, datetime, timedelta

from app.config import Settings, get_settings

log = logging.getLogger(__name__)
INTERVAL_SECONDS = 24 * 60 * 60


def cutoffs(settings: Settings, now: datetime) -> tuple[datetime | None, datetime | None]:
    def cutoff(days: int) -> datetime | None:
        return now - timedelta(days=days) if days > 0 else None

    return cutoff(settings.log_retention_days), cutoff(settings.request_log_retention_days)


def purge(db, settings: Settings, now: datetime | None = None) -> dict[str, int]:
    log_cutoff, request_cutoff = cutoffs(settings, now or datetime.now(UTC))
    deleted = db.purge_older_than(log_cutoff, request_cutoff)
    log.info("retention cleanup deleted %s", deleted)
    return deleted


def start_daily_purge(get_db, settings: Settings) -> threading.Event:
    """Run purge now and then every 24 hours in a daemon thread. Set the returned event to stop it."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                purge(get_db(), settings)
            except Exception:  # a failed cleanup must not take the API down; it retries next cycle
                log.exception("retention cleanup failed")
            stop.wait(INTERVAL_SECONDS)

    threading.Thread(target=loop, name="retention", daemon=True).start()
    return stop


def main() -> int:
    from app.db import get_db

    db = get_db()
    try:
        print(purge(db, get_settings()))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
