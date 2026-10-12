from datetime import UTC, datetime, timedelta

from app.ratelimit import MemoryRequestStore, RateLimiter, hash_ip


class Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def test_per_ip_limit_blocks_after_n_requests_in_an_hour():
    clock = Clock(datetime(2026, 10, 1, 10, 0, tzinfo=UTC))
    limiter = RateLimiter(MemoryRequestStore(), per_hour=3, daily_cap=100, clock=clock)
    assert all(limiter.check_and_record("ip1", "halden").allowed for _ in range(3))
    blocked = limiter.check_and_record("ip1", "halden")
    assert not blocked.allowed and blocked.reason == "rate_limited"
    assert limiter.check_and_record("ip2", "halden").allowed, "other IPs are not affected"


def test_per_ip_window_slides():
    clock = Clock(datetime(2026, 10, 1, 10, 0, tzinfo=UTC))
    limiter = RateLimiter(MemoryRequestStore(), per_hour=2, daily_cap=100, clock=clock)
    limiter.check_and_record("ip1", "halden")
    clock.now += timedelta(minutes=30)
    limiter.check_and_record("ip1", "halden")
    assert not limiter.check_and_record("ip1", "halden").allowed
    clock.now += timedelta(minutes=31)
    assert limiter.check_and_record("ip1", "halden").allowed


def test_daily_cap_applies_across_ips_and_resets_at_midnight_utc():
    clock = Clock(datetime(2026, 10, 1, 23, 0, tzinfo=UTC))
    limiter = RateLimiter(MemoryRequestStore(), per_hour=100, daily_cap=3, clock=clock)
    for ip in ("a", "b", "c"):
        assert limiter.check_and_record(ip, "halden").allowed
    capped = limiter.check_and_record("d", "fastapi")
    assert not capped.allowed and capped.reason == "daily_cap"
    assert capped.retry_after_seconds == 3600
    clock.now = datetime(2026, 10, 2, 0, 1, tzinfo=UTC)
    assert limiter.check_and_record("d", "fastapi").allowed


def test_blocked_requests_are_not_counted():
    clock = Clock(datetime(2026, 10, 1, 10, 0, tzinfo=UTC))
    store = MemoryRequestStore()
    limiter = RateLimiter(store, per_hour=1, daily_cap=100, clock=clock)
    limiter.check_and_record("ip1", "halden")
    for _ in range(5):
        limiter.check_and_record("ip1", "halden")
    assert len(store.events) == 1


def test_zero_disables_limits():
    limiter = RateLimiter(MemoryRequestStore(), per_hour=0, daily_cap=0)
    assert all(limiter.check_and_record("ip", "halden").allowed for _ in range(50))


def test_ip_hash_is_salted_and_not_reversible_text():
    h = hash_ip("203.0.113.5", "salt")
    assert "203" not in h and len(h) == 32
    assert h != hash_ip("203.0.113.5", "other-salt")
