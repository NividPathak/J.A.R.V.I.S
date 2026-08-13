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
        lines = [
            f"Now: {now.strftime('%A %-d %B, %-I:%M %p')}",
            # Stated per-request as well as in the persona. Asked to "set a
            # reminder", the model confidently claimed it had scheduled one and
            # that "the calendar has been updated" — with no write path at all.
            "This calendar view is READ-ONLY. You cannot add, move, delete or "
            "remind. If asked to, say so and suggest doing it in Calendar.app.",
            self._staleness_note(),
            "",
        ]

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

    def brief(self) -> str:
        entry = self._cache.get("calendar")
        if entry is None or not entry.payload:
            return "Your calendar is unavailable."

        now = datetime.now()
        today = entry.payload.get("today") or []
        timed = sorted(
            (e for e in today if not e["all_day"]),
            key=lambda e: e["start"],
        )
        all_day = [e for e in today if e["all_day"]]

        lines: list[str] = []
        if all_day:
            lines.append("Today is " + ", ".join(e["title"] for e in all_day[:3]) + ".")

        if not timed:
            lines.append("Nothing scheduled today.")
        else:
            lines.append(f"{len(timed)} thing{'s' if len(timed) != 1 else ''} on today:")
            for event in timed[:6]:
                start = datetime.fromisoformat(event["start"]).strftime("%-I:%M %p").lower()
                where = f", {event['location']}" if event.get("location") else ""
                lines.append(f"  {start} — {event['title']}{where}")

        # A quiet today says nothing about tomorrow, and knowing tonight is the
        # point of a morning briefing.
        upcoming = entry.payload.get("next")
        if upcoming and not any(e["start"] == upcoming["start"] for e in timed):
            lines.append(f"Next after that: {upcoming['title']} {describe_when(upcoming, now)}.")
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
