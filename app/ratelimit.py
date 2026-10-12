"""Per-IP rate limit and a global daily request cap for the public demo."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


class RequestStore(Protocol):
    def count_requests(self, since: datetime, ip_hash: str | None = None) -> int: ...

    def record_request(self, dataset: str, ip_hash: str, at: datetime) -> None: ...


class MemoryRequestStore:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, datetime]] = []

    def count_requests(self, since: datetime, ip_hash: str | None = None) -> int:
        return sum(1 for _, ip, at in self.events if at >= since and (ip_hash is None or ip == ip_hash))

    def record_request(self, dataset: str, ip_hash: str, at: datetime) -> None:
        self.events.append((dataset, ip_hash, at))


@dataclass
class LimitDecision:
    allowed: bool
    reason: str | None = None  # "rate_limited" or "daily_cap"
    retry_after_seconds: int = 0


def hash_ip(ip: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:32]


class RateLimiter:
    def __init__(
        self,
        store: RequestStore,
        per_hour: int,
        daily_cap: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.store = store
        self.per_hour = per_hour
        self.daily_cap = daily_cap
        self.clock = clock

    def check_and_record(self, ip_hash: str, dataset: str) -> LimitDecision:
        now = self.clock()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.daily_cap > 0 and self.store.count_requests(midnight) >= self.daily_cap:
            return LimitDecision(False, "daily_cap", int((midnight + timedelta(days=1) - now).total_seconds()))
        if self.per_hour > 0 and self.store.count_requests(now - timedelta(hours=1), ip_hash) >= self.per_hour:
            return LimitDecision(False, "rate_limited", 3600)
        self.store.record_request(dataset, ip_hash, now)
        return LimitDecision(True)
