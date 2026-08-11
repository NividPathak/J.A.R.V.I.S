"""NBA data via nba_api — free, no key.

Ported from the previous build. Two changes on the way in:
  * the season is computed rather than hardcoded (it had drifted two seasons stale)
  * everything returns structured data instead of pre-formatted strings, so the
    cache can serve both the agent and the dashboard
"""
from datetime import datetime
from typing import Any

# nba_api game status codes
STATUS_SCHEDULED, STATUS_LIVE, STATUS_FINAL = 1, 2, 3


def current_season(now: datetime | None = None) -> str:
    """NBA seasons span Oct-Jun, so the label depends on which side of Oct we're on.

    >>> current_season(datetime(2026, 8, 11))
    '2025-26'
    >>> current_season(datetime(2026, 11, 3))
    '2026-27'
    """
    now = now or datetime.now()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def todays_games() -> list[dict[str, Any]]:
    """Today's games as structured records. Raises if nba_api is unavailable."""
    from nba_api.live.nba.endpoints import scoreboard

    games = scoreboard.ScoreBoard().games.get_dict()
    return [
        {
            "game_id": g.get("gameId"),
            "status": g.get("gameStatus"),
            "status_text": (g.get("gameStatusText") or "").strip(),
            "start_et": g.get("gameEt"),
            "home": _team(g["homeTeam"]),
            "away": _team(g["awayTeam"]),
        }
        for g in games
    ]


def standings() -> dict[str, list[dict[str, Any]]]:
    """Top 8 per conference, structured."""
    from nba_api.stats.endpoints import leaguestandings

    df = leaguestandings.LeagueStandings(season=current_season()).get_data_frames()[0]
    return {
        conf.lower(): [
            {
                "rank": int(row.get("PlayoffRank", 0)),
                "team": f"{row['TeamCity']} {row['TeamName']}",
                "wins": int(row["WINS"]),
                "losses": int(row["LOSSES"]),
            }
            for _, row in df[df["Conference"] == conf].head(8).iterrows()
        ]
        for conf in ("East", "West")
    }


def box_score(game_id: str) -> dict[str, Any]:
    """Live box score for one game."""
    from nba_api.live.nba.endpoints import boxscore

    box = boxscore.BoxScore(game_id=game_id)
    return {"home": _team(box.home_team.get_dict()), "away": _team(box.away_team.get_dict())}


def _team(t: dict) -> dict[str, Any]:
    score = t.get("score")
    return {
        "city": t.get("teamCity"),
        "name": t.get("teamName"),
        "tricode": t.get("teamTricode"),
        "score": int(score) if isinstance(score, (int, str)) and str(score).isdigit() else None,
    }
