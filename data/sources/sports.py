"""Sports sources.

Three shapes, because the sports genuinely differ:

  EspnSource     NBA/NFL — scoreboard plus per-event box scores and scoring plays
  CricketSource  several ESPN leagues merged, so internationals and franchise
                 cricket appear together rather than one being picked
  F1Source       Jolpica for classified results, OpenF1 for flags — ESPN returns
                 empty statistics for motorsport

Detail is fetched for at most a few events per poll. Enriching a full slate
would be dozens of extra calls for rows nobody scrolls to.
"""
import logging
from typing import Any

from data.cache import Entry
from data.sources.base import Source
from integrations import espn, f1

log = logging.getLogger("jarvis.sports")

LIVE_INTERVAL = 60.0
EVENT_DAY_INTERVAL = 900.0
IDLE_INTERVAL = 21600.0
DETAIL_EVENTS = 3


class EspnSource(Source):
    """A sport served by ESPN's scoreboard, optionally enriched per event."""

    daily_budget = None
    ttl = LIVE_INTERVAL

    def __init__(self, name: str, path: str, label: str, detail: bool = True):
        self.name, self.path, self.label, self.detail = name, path, label, detail

    def fetch(self) -> dict[str, Any]:
        events = espn.scoreboard(self.path)
        if self.detail:
            self._enrich(events)
        return {"label": self.label, "events": events, "live": espn.is_live(events)}

    def _enrich(self, events: list[dict[str, Any]]) -> None:
        """Attach box score and scoring plays to the events worth showing.

        Live games first, then anything already played — an unplayed fixture has
        no detail to fetch. Failures are logged and skipped: missing detail
        should cost a panel, not the whole source.
        """
        ordered = sorted(events, key=lambda e: 0 if e["state"] == espn.LIVE else 1)
        for event in [e for e in ordered if e["state"] != espn.PRE][:DETAIL_EVENTS]:
            try:
                event["stats"] = espn.summary(self.path, event["id"])
            except Exception as e:
                log.debug("no detail for %s %s: %s", self.name, event.get("id"), e)

    def interval(self, last: Entry | None) -> float:
        if last is None or not last.payload:
            return EVENT_DAY_INTERVAL
        if last.payload.get("live"):
            return LIVE_INTERVAL
        return EVENT_DAY_INTERVAL if last.payload.get("events") else IDLE_INTERVAL


#: ESPN scopes cricket by league, so one id is one competition. Internationals
#: come first — a bare `cricket` path 404s, and polling only the IPL meant the
#: board showed a franchise final months after the season ended.
CRICKET_LEAGUES = [
    ("19430", "ICC World Test Championship"),
    ("19439", "ICC Men's CWC League 2"),
    ("8052", "County Championship"),
    ("8048", "Indian Premier League"),
    ("8044", "Big Bash League"),
]


class CricketSource(Source):
    name = "cricket"
    label = "Cricket"
    ttl = LIVE_INTERVAL
    daily_budget = None

    def __init__(self, leagues: list[tuple[str, str]] | None = None):
        self.leagues = leagues or CRICKET_LEAGUES

    def fetch(self) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        failed: list[str] = []
        for league_id, label in self.leagues:
            try:
                for event in espn.scoreboard(f"{espn.CRICKET}/{league_id}"):
                    event["competition"] = label
                    event["international"] = label.startswith("ICC")
                    events.append(event)
            except Exception as e:
                failed.append(f"{label}: {type(e).__name__}")

        if not events and failed:
            raise RuntimeError("; ".join(failed))

        # Live first, then most recent — an international Test outranks a
        # franchise fixture from three months ago.
        events.sort(key=lambda e: (e["state"] != espn.LIVE, e.get("start") or ""), reverse=False)
        events.sort(key=lambda e: e["state"] == espn.LIVE, reverse=True)
        return {
            "label": self.label,
            "events": events,
            "live": espn.is_live(events),
            "leagues_failed": failed,
        }

    def interval(self, last: Entry | None) -> float:
        if last is None or not last.payload:
            return EVENT_DAY_INTERVAL
        return LIVE_INTERVAL if last.payload.get("live") else EVENT_DAY_INTERVAL


class F1Source(Source):
    """Formula 1. ESPN returns empty statistics for motorsport, so this uses
    Jolpica for the classification and OpenF1 for race control."""

    name = "f1"
    label = "Formula 1"
    ttl = EVENT_DAY_INTERVAL
    #: Jolpica allows 200/hour unauthenticated; this pacing uses a handful.
    daily_budget = 300

    def fetch(self) -> dict[str, Any]:
        upcoming = espn.scoreboard(espn.F1)
        race = f1.last_race()
        return {
            "label": self.label,
            "events": upcoming,
            "live": espn.is_live(upcoming),
            "last_race": race,
            "race_control": f1.race_control() if race else [],
        }

    def interval(self, last: Entry | None) -> float:
        if last and last.payload and last.payload.get("live"):
            return LIVE_INTERVAL
        return EVENT_DAY_INTERVAL


def nba() -> EspnSource:
    return EspnSource("nba", espn.NBA, "NBA")


def nfl() -> EspnSource:
    return EspnSource("nfl", espn.NFL, "NFL")


def f1_source() -> F1Source:
    return F1Source()


def cricket() -> CricketSource:
    return CricketSource()
