"""The Source contract.

A Source knows how to fetch one upstream and how often it's allowed to.
It returns structured data, never display strings — formatting belongs at the
edge (agent for conversation, dashboard for rendering), so the same cached
payload serves both.
"""
from abc import ABC, abstractmethod
from typing import Any

from data.cache import Entry

DAY = 86400.0


class Source(ABC):
    #: cache key
    name: str
    #: how long a payload stays fresh, seconds
    ttl: float
    #: max calls/day this source's free tier allows. None = effectively unlimited.
    daily_budget: int | None = None

    @abstractmethod
    def fetch(self) -> Any:
        """Hit the upstream and return a JSON-serialisable payload.

        Raise on failure — the poller catches it and preserves the last good
        payload rather than overwriting it with an error.
        """

    def interval(self, last: Entry | None) -> float:
        """Seconds until the next poll.

        Override to pace dynamically — most sports are worth polling hard during
        a live event and barely at all otherwise. Default is a steady `ttl`.
        """
        return self.ttl

    def validate_budget(self) -> str | None:
        """Catch an interval that would blow the free tier, before it does.

        Returns a warning string, or None if the pacing is safe. Checked at
        poller startup — cheap insurance against a one-character mistake
        exhausting a 100/day quota in an afternoon.
        """
        if self.daily_budget is None:
            return None
        fastest = self.interval(None)
        if fastest <= 0:
            return f"{self.name}: interval must be positive"
        projected = DAY / fastest
        if projected > self.daily_budget:
            return (
                f"{self.name}: pacing at {fastest:.0f}s = ~{projected:.0f} calls/day, "
                f"over the {self.daily_budget}/day budget"
            )
        return None
