"""NBA source — the reference implementation for the Source contract.

nba_api has no published rate limit, but the dynamic interval here is the
pattern every other sport follows: poll hard only while something is actually
happening. It's what lets cricket live inside 100 calls/day.
"""
from typing import Any

from data.cache import Entry
from data.sources.base import Source
from integrations import espn, nba_client

LIVE_INTERVAL = 60.0  # a game is in progress
GAMEDAY_INTERVAL = 900.0  # games scheduled today, none tipped off yet
IDLE_INTERVAL = 21600.0  # nothing on — offseason, or an off day


class NBASource(Source):
    name = "nba"
    ttl = LIVE_INTERVAL
    daily_budget = None

    def fetch(self) -> dict[str, Any]:
        # Games from ESPN (nba.com's live CDN 403s non-browser clients);
        # standings from nba_api, which serves them cleanly and needs no key.
        games = espn.scoreboard(espn.NBA)
        return {
            "games": games,
            "standings": nba_client.standings(),
            "live": espn.is_live(games),
        }

    def interval(self, last: Entry | None) -> float:
        """Match the poll rate to what's actually happening on the court."""
        if last is None or not last.payload:
            return GAMEDAY_INTERVAL
        if last.payload.get("live"):
            return LIVE_INTERVAL
        return GAMEDAY_INTERVAL if last.payload.get("games") else IDLE_INTERVAL
