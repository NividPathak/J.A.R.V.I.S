"""ESPN-backed sports sources.

One parameterised class rather than a file per sport — ESPN returns an identical
shape for all of them, so NFL, F1 and cricket differ only by path and name.
NBA keeps its own module because it also pulls standings from nba_api.

Cricket is league-scoped: the bare `cricket` path 404s, so a league id is
required. 8048 is verified working; add the leagues worth following.
"""
from typing import Any

from data.cache import Entry
from data.sources.base import Source
from integrations import espn

LIVE_INTERVAL = 60.0
EVENT_DAY_INTERVAL = 900.0
IDLE_INTERVAL = 21600.0


class EspnSource(Source):
    """A sport whose entire feed is ESPN's scoreboard."""

    daily_budget = None
    ttl = LIVE_INTERVAL

    def __init__(self, name: str, path: str, label: str):
        self.name = name
        self.path = path
        self.label = label

    def fetch(self) -> dict[str, Any]:
        events = espn.scoreboard(self.path)
        return {"label": self.label, "events": events, "live": espn.is_live(events)}

    def interval(self, last: Entry | None) -> float:
        if last is None or not last.payload:
            return EVENT_DAY_INTERVAL
        if last.payload.get("live"):
            return LIVE_INTERVAL
        return EVENT_DAY_INTERVAL if last.payload.get("events") else IDLE_INTERVAL


def nfl() -> EspnSource:
    return EspnSource("nfl", espn.NFL, "NFL")


def f1() -> EspnSource:
    return EspnSource("f1", espn.F1, "Formula 1")


def cricket(league: str = "8048") -> EspnSource:
    return EspnSource("cricket", f"{espn.CRICKET}/{league}", "Cricket")
