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
