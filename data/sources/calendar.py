"""Calendar source.

The AppleScript query is slow (~18s), which is exactly why it belongs behind the
poller: the cost is paid in the background and the agent reads the cache in
microseconds. Reads come from cache; any future *write* (creating an event) must
go direct, since a stale confirmation would be worse than a slow one.
"""
from typing import Any

from data.cache import Entry
from data.sources.base import Source
from integrations import calendar_mac

LOOKAHEAD_DAYS = 14
INTERVAL = 600.0  # 10 min — calendars don't change faster than you can act on


class CalendarSource(Source):
    name = "calendar"
    ttl = INTERVAL
    daily_budget = None

    def fetch(self) -> dict[str, Any]:
        events = calendar_mac.upcoming(days=LOOKAHEAD_DAYS)
        return {
            "events": events,
            "today": calendar_mac.today(events),
            "next": calendar_mac.next_event(events),
        }

    def interval(self, last: Entry | None) -> float:
        return INTERVAL
