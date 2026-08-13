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


def summary(sport_path: str, event_id: str) -> dict[str, Any]:
    """Per-event detail: box score, statistical leaders, and scoring plays.

    A separate request per event, which is why only the handful of events the
    dashboard actually shows get enriched — fetching detail for a full slate
    would be dozens of calls per poll for data nobody looks at.
    """
    r = requests.get(f"{BASE}/{sport_path}/summary", params={"event": event_id}, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return {
        "leaders": _leaders(d.get("leaders") or []),
        "players": _players(((d.get("boxscore") or {}).get("players")) or []),
        "scoring": _scoring(d.get("scoringPlays") or []),
    }


def _leaders(raw: list[dict]) -> list[dict[str, Any]]:
    """Per-team statistical leaders — the 'who's performing' line."""
    out = []
    for team in raw:
        entries = []
        for category in team.get("leaders") or []:
            for leader in (category.get("leaders") or [])[:1]:
                athlete = leader.get("athlete") or {}
                entries.append({
                    "category": category.get("displayName") or category.get("name"),
                    "athlete": athlete.get("shortName") or athlete.get("displayName"),
                    "value": leader.get("displayValue"),
                })
        if entries:
            out.append({"team": (team.get("team") or {}).get("abbreviation"), "entries": entries[:4]})
    return out


def _players(raw: list[dict]) -> list[dict[str, Any]]:
    """Box score rows, trimmed to the top scorers.

    Keeps the stat labels alongside the values — they differ by sport (NBA gives
    PTS/FG/3PT, NFL gives passing splits), so hardcoding column names here would
    break the moment a second sport used it.
    """
    out = []
    for team in raw:
        block = (team.get("statistics") or [{}])[0]
        labels = block.get("labels") or []
        rows = []
        for athlete in block.get("athletes") or []:
            stats = athlete.get("stats") or []
            if not stats:
                continue
            info = athlete.get("athlete") or {}
            rows.append({
                "name": info.get("shortName") or info.get("displayName"),
                "position": (info.get("position") or {}).get("abbreviation"),
                "stats": dict(zip(labels, stats)),
                "starter": athlete.get("starter", False),
            })
        if rows:
            key = "PTS" if "PTS" in labels else (labels[1] if len(labels) > 1 else None)
            if key:
                rows.sort(key=lambda r: _num(r["stats"].get(key)), reverse=True)
            out.append({
                "team": (team.get("team") or {}).get("abbreviation"),
                "labels": labels,
                "players": rows[:5],
            })
    return out


def _scoring(raw: list[dict]) -> list[dict[str, Any]]:
    """Who scored and how — the narrative of the game, not just the total."""
    return [{
        "team": (p.get("team") or {}).get("abbreviation"),
        "type": (p.get("scoringType") or {}).get("abbreviation"),
        "period": (p.get("period") or {}).get("number"),
        "clock": (p.get("clock") or {}).get("displayValue"),
        "text": p.get("text"),
        "away_score": p.get("awayScore"),
        "home_score": p.get("homeScore"),
    } for p in raw]


def _num(v: Any) -> float:
    try:
        return float(str(v).split("-")[0])
    except (TypeError, ValueError):
        return -1.0


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
