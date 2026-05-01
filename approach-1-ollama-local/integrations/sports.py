"""Sports data via nba_api — free, no key needed, real-time NBA data."""
from datetime import datetime


def _try_import():
    try:
        from nba_api.live.nba.endpoints import scoreboard, boxscore
        from nba_api.stats.endpoints import playoffpicture, leaguestandings
        return scoreboard, boxscore, playoffpicture, leaguestandings
    except ImportError:
        return None, None, None, None


def nba_today() -> str:
    """Get today's NBA games — scores, status, teams."""
    scoreboard_ep, _, _, _ = _try_import()
    if not scoreboard_ep:
        return "nba_api not installed. Run: pip install nba_api"
    try:
        board = scoreboard_ep.ScoreBoard()
        games = board.games.get_dict()
        if not games:
            return "No NBA games scheduled today."

        today = datetime.now().strftime("%A, %B %d")
        lines = [f"NBA Games — {today}\n"]
        for g in games:
            home = g["homeTeam"]
            away = g["awayTeam"]
            status = g.get("gameStatusText", "").strip()
            home_score = home.get("score", "")
            away_score = away.get("score", "")

            if home_score or away_score:
                score_str = f"{away_score} – {home_score}"
                lines.append(f"  {away['teamCity']} {away['teamName']} vs {home['teamCity']} {home['teamName']}")
                lines.append(f"  Score: {score_str}  |  {status}\n")
            else:
                game_time = g.get("gameEt", status)
                lines.append(f"  {away['teamCity']} {away['teamName']} @ {home['teamCity']} {home['teamName']}")
                lines.append(f"  {game_time}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to get NBA games: {e}"


def nba_standings() -> str:
    """Get current NBA playoff standings."""
    _, _, _, standings_ep = _try_import()
    if not standings_ep:
        return "nba_api not installed."
    try:
        standings = standings_ep.LeagueStandings(season="2024-25")
        data = standings.get_data_frames()[0]
        east = data[data["Conference"] == "East"].head(8)
        west = data[data["Conference"] == "West"].head(8)

        lines = ["NBA Playoff Picture\n", "── EAST ──"]
        for _, row in east.iterrows():
            lines.append(f"  {int(row.get('PlayoffRank', 0)):>2}. {row['TeamCity']} {row['TeamName']}  {row['WINS']}-{row['LOSSES']}")

        lines.append("\n── WEST ──")
        for _, row in west.iterrows():
            lines.append(f"  {int(row.get('PlayoffRank', 0)):>2}. {row['TeamCity']} {row['TeamName']}  {row['WINS']}-{row['LOSSES']}")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to get standings: {e}"


def nba_live_score(game_id: str) -> str:
    """Get live box score for a specific game by ID."""
    _, boxscore_ep, _, _ = _try_import()
    if not boxscore_ep:
        return "nba_api not installed."
    try:
        box = boxscore_ep.BoxScore(game_id=game_id)
        home = box.home_team.get_dict()
        away = box.away_team.get_dict()
        return (
            f"{away['teamCity']} {away['teamName']}: {away.get('score', '?')}\n"
            f"{home['teamCity']} {home['teamName']}: {home.get('score', '?')}"
        )
    except Exception as e:
        return f"Failed to get box score: {e}"
