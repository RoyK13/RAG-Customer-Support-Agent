from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.retention import cutoffs, purge

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


class RecordingDB:
    def __init__(self):
        self.calls = []

    def purge_older_than(self, log_cutoff, request_cutoff):
        self.calls.append((log_cutoff, request_cutoff))
        return {"chat_turns": 0, "escalations": 0, "request_log": 0}


def test_cutoffs_follow_settings():
    log_cut, req_cut = cutoffs(Settings(log_retention_days=30, request_log_retention_days=2), NOW)
    assert log_cut == NOW - timedelta(days=30)
    assert req_cut == NOW - timedelta(days=2)


def test_zero_days_keeps_data_forever():
    assert cutoffs(Settings(log_retention_days=0, request_log_retention_days=0), NOW) == (None, None)


def test_purge_passes_cutoffs_to_db():
    db = RecordingDB()
    purge(db, Settings(log_retention_days=30, request_log_retention_days=2), now=NOW)
    assert db.calls == [(NOW - timedelta(days=30), NOW - timedelta(days=2))]
