"""ESPN's public scoreboard API — free, no key, one shape for every sport.

Chosen over nba.com's live CDN, which returns 403 to non-browser clients. ESPN
covers NBA, NFL, F1 and cricket behind identical JSON, so one client and one
normaliser serve every sport the briefing and dashboard need.

Undocumented but long-stable and widely used. If it ever moves, the blast radius
is this file.
"""
from typing import Any

import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports"
TIMEOUT = 15

# ESPN's sport/league path segments.
NBA = "basketball/nba"
NFL = "football/nfl"
F1 = "racing/f1"
CRICKET = "cricket"

#: status.type.state values, uniform across sports
PRE, LIVE, FINAL = "pre", "in", "post"


def scoreboard(sport_path: str, **params: Any) -> list[dict[str, Any]]:
    """Normalised events for a sport. Raises on transport or HTTP error."""
    r = requests.get(f"{BASE}/{sport_path}/scoreboard", params=params or None, timeout=TIMEOUT)
    r.raise_for_status()
    return [_event(e) for e in r.json().get("events", [])]


def is_live(events: list[dict[str, Any]]) -> bool:
    return any(e["state"] == LIVE for e in events)


def _event(ev: dict) -> dict[str, Any]:
    status = (ev.get("status") or {}).get("type") or {}
    competitions = ev.get("competitions") or [{}]
    return {
        "id": ev.get("id"),
        "name": ev.get("name"),
        "short_name": ev.get("shortName"),
        "start": ev.get("date"),
        "state": status.get("state"),
        "completed": status.get("completed", False),
        "detail": status.get("shortDetail") or status.get("detail"),
        "competitors": [_competitor(c) for c in competitions[0].get("competitors", [])],
    }


def _competitor(c: dict) -> dict[str, Any]:
    team = c.get("team") or {}
    score = c.get("score")
    return {
        "side": c.get("homeAway"),
        "name": team.get("displayName") or team.get("name"),
        "abbr": team.get("abbreviation"),
        "score": int(score) if isinstance(score, str) and score.isdigit() else score,
        "winner": c.get("winner"),
    }
