"""Calendar agent — the user's own schedule."""
from datetime import datetime

from agents.base import CachedAgent
from integrations.calendar_mac import describe_when


class CalendarAgent(CachedAgent):
    name = "calendar"
    description = "your calendar — meetings, scheduling, availability"
    sources = ("calendar",)

    def context(self) -> str:
        entry = self._cache.get("calendar")
        if entry is None or not entry.payload:
            return ""

        payload = entry.payload
        now = datetime.now()
        lines = [f"Now: {now.strftime('%A %-d %B, %-I:%M %p')}", self._staleness_note(), ""]

        upcoming = payload.get("next")
        lines.append(
            f"Next timed event: {upcoming['title']} {describe_when(upcoming, now)}"
            if upcoming else "Next timed event: none scheduled"
        )

        lines.append("")
        lines.append("Upcoming events:")
        events = payload.get("events") or []
        if not events:
            lines.append("  (nothing in the next two weeks)")
        for event in events[:15]:
            when = describe_when(event, now)
            where = f" at {event['location']}" if event.get("location") else ""
            marker = " [all-day]" if event["all_day"] else ""
            lines.append(f"  - {event['title']}{marker} — {when}{where} [{event['calendar']}]")
        return "\n".join(lines)

    def summary(self) -> str:
        entry = self._cache.get("calendar")
        if entry is None or not entry.payload:
            return "Calendar unavailable."

        today = entry.payload.get("today") or []
        timed = [e for e in today if not e["all_day"]]
        all_day = [e for e in today if e["all_day"]]

        if not today:
            return "Nothing on your calendar today."

        parts = []
        if timed:
            first = timed[0]
            start = datetime.fromisoformat(first["start"]).strftime("%-I:%M %p").lower()
            parts.append(
                f"{len(timed)} meeting{'s' if len(timed) != 1 else ''} today, "
                f"first is {first['title']} at {start}"
            )
        if all_day:
            parts.append(", ".join(e["title"] for e in all_day[:3]))
        return ". ".join(parts) + "."
