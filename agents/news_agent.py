"""News agent — headlines and sport.

One agent covering both, per the design. The router still labels them as
separate intents, so splitting this into two agents later needs only a change to
AGENT_FOR — the eval corpus stays valid.
"""
from agents.base import CachedAgent

SPORT_SOURCES = ("nba", "nfl", "f1", "cricket")
SPORT_LABELS = {"nba": "NBA", "nfl": "NFL", "f1": "Formula 1", "cricket": "Cricket"}
STATE_WORD = {"pre": "upcoming", "in": "LIVE", "post": "final"}


class NewsAgent(CachedAgent):
    name = "news"
    description = "news headlines and sport — NBA, NFL, F1, cricket"
    sources = ("news",) + SPORT_SOURCES

    def context(self) -> str:
        parts = [self._staleness_note(), self._headlines_block(), self._sports_block()]
        return "\n".join(p for p in parts if p.strip())

    def _headlines_block(self) -> str:
        entry = self._cache.get("news")
        if entry is None or not entry.payload:
            return ""
        # Deliberately few. The full cache holds ~30 headlines, but stuffing all
        # of them into the prompt roughly doubled agent latency on the local
        # model for no gain — nobody asks for the 27th story.
        lines = ["HEADLINES:"]
        for topic, items in (entry.payload.get("by_topic") or {}).items():
            lines.append(f"  {topic}:")
            lines.extend(f"    - {h['title']} ({h['source']})" for h in items[:4])
        return "\n".join(lines)

    def _sports_block(self) -> str:
        lines = ["", "SPORT:"]
        found = False
        for key in SPORT_SOURCES:
            entry = self._cache.get(key)
            if entry is None or not entry.payload:
                continue
            events = entry.payload.get("events") or entry.payload.get("games") or []
            if not events:
                continue
            found = True
            lines.append(f"  {SPORT_LABELS[key]}:")
            for event in events[:4]:
                lines.append(f"    - {self._describe(event)}")

            standings = entry.payload.get("standings")
            if standings:
                for conference, teams in standings.items():
                    top = ", ".join(f"{t['team']} {t['wins']}-{t['losses']}" for t in teams[:3])
                    lines.append(f"    {conference} leaders: {top}")
        return "\n".join(lines) if found else ""

    @staticmethod
    def _describe(event: dict) -> str:
        """One event line, always carrying its date.

        The date is not decoration. Out-of-season leagues keep returning their
        last completed fixture — ESPN served a May IPL final as the current
        cricket scoreboard — and without a date the model presents it as today's
        result. With one, it can say the match was months ago.
        """
        state = STATE_WORD.get(event.get("state"), event.get("state") or "")
        name = event.get("short_name") or event.get("name") or "?"
        when = (event.get("start") or "")[:10]
        scores = " ".join(
            f"{c['abbr'] or c['name']} {c['score']}"
            for c in event.get("competitors", [])
            if c.get("score") is not None
        )
        detail = event.get("detail") or ""
        return (
            f"[{state}] {when} {name}"
            + (f" — {scores}" if scores else "")
            + (f" ({detail})" if detail else "")
        )

    def brief(self) -> str:
        from datetime import date, timedelta

        lines: list[str] = []
        today = date.today()
        # A briefing wants last night's results and today's fixtures — bounded
        # at both ends. Without an upper bound an out-of-season league's next
        # season opener reads as though it were tonight.
        window = (str(today - timedelta(days=1)), str(today + timedelta(days=1)))

        for key in SPORT_SOURCES:
            entry = self._cache.get(key)
            if entry is None or not entry.payload:
                continue
            events = entry.payload.get("events") or entry.payload.get("games") or []
            current = [e for e in events if window[0] <= (e.get("start") or "")[:10] <= window[1]]
            for event in current[:3]:
                lines.append(f"  {SPORT_LABELS[key]}: {self._brief_line(event)}")

        if lines:
            lines.insert(0, "Sport:")

        news = self._cache.get("news")
        if news and news.payload:
            headlines = (news.payload.get("headlines") or [])[:3]
            if headlines:
                if lines:
                    lines.append("")
                lines.append("Headlines:")
                lines.extend(f"  {h['title']} ({h['source']})" for h in headlines)

        return "\n".join(lines) if lines else "No news or sport cached."

    @staticmethod
    def _brief_line(event: dict) -> str:
        """Human phrasing for the briefing.

        `_describe` exists for the model and carries brackets, ISO dates and
        state codes. None of that survives being read aloud, so the briefing
        gets its own rendering rather than reusing it.
        """
        competitors = event.get("competitors", [])
        scored = [c for c in competitors if c.get("score") is not None]
        name = event.get("short_name") or event.get("name") or "match"
        state = event.get("state")

        if state == "post" and len(scored) == 2:
            winner = next((c for c in scored if c.get("winner") in (True, "true")), None)
            loser = next((c for c in scored if c is not winner), None)
            if winner and loser:
                return f"{winner['name']} beat {loser['name']}, {winner['score']} to {loser['score']}"
            return f"{name} finished {' - '.join(str(c['score']) for c in scored)}"

        if state == "in":
            live = ", ".join(f"{c['name']} {c['score']}" for c in scored)
            return f"{live} — in progress" if live else f"{name} under way"

        detail = event.get("detail") or "later"
        return f"{name}, {detail}"

    def summary(self) -> str:
        bits = []
        news = self._cache.get("news")
        if news and news.payload:
            headlines = news.payload.get("headlines") or []
            if headlines:
                bits.append("Top story: " + headlines[0]["title"])

        live = []
        for key in SPORT_SOURCES:
            entry = self._cache.get(key)
            if entry and entry.payload and entry.payload.get("live"):
                live.append(SPORT_LABELS[key])
        if live:
            bits.append(f"Live now: {', '.join(live)}.")
        return " ".join(bits) or "No headlines cached."
