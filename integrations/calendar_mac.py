"""macOS Calendar.app via AppleScript.

Reads whatever is already in Calendar.app — which on this machine includes the
synced Google account, so there's no OAuth flow, no credentials file and no
token refresh to maintain. Local and private.

The query takes ~15-20s, which is why calendar is a *Source*: the poller absorbs
that in the background and the agent reads the cache instantly. EventKit is far
faster but only saw 1 of 8 calendars under the current TCC grant, so it isn't
worth the permission complexity yet.

Dates are emitted as explicit components rather than formatted strings —
AppleScript's date rendering is locale-dependent and miserable to parse back.
"""
import subprocess
from datetime import datetime, timedelta
from typing import Any

FIELD, RECORD = "\t", "\n"
QUERY_TIMEOUT = 120

# `whose` filtering happens inside Calendar.app, which is much faster than
# pulling every event into AppleScript and filtering there.
SCRIPT = """
on isoish(d)
  return (year of d as string) & "," & (month of d as integer as string) & "," & ¬
         (day of d as string) & "," & (hours of d as string) & "," & (minutes of d as string)
end isoish

set out to ""
set startDate to (current date)
set endDate to startDate + (%(days)d * days)
tell application "Calendar"
  repeat with c in calendars
    try
      set evs to (every event of c whose start date >= startDate and start date <= endDate)
      repeat with e in evs
        set out to out & (name of c) & "\t" & (summary of e) & "\t" & ¬
          my isoish(start date of e) & "\t" & my isoish(end date of e) & "\t" & ¬
          (allday event of e as string) & "\t" & (location of e as string) & "\n"
      end repeat
    end try
  end repeat
end tell
return out
"""


def upcoming(days: int = 7) -> list[dict[str, Any]]:
    """Events between now and `days` ahead, across every calendar. Raises on failure."""
    result = subprocess.run(
        ["osascript", "-e", SCRIPT % {"days": days}],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Calendar query failed: {result.stderr.strip()[:200]}")

    events = [e for e in (_parse(line) for line in result.stdout.split(RECORD)) if e]
    events.sort(key=lambda e: e["start"])
    return events


def _parse(line: str) -> dict[str, Any] | None:
    parts = line.split(FIELD)
    if len(parts) < 5:
        return None
    calendar, summary, start_raw, end_raw, all_day = parts[:5]
    location = parts[5].strip() if len(parts) > 5 else ""
    try:
        start, end = _to_datetime(start_raw), _to_datetime(end_raw)
    except (ValueError, IndexError):
        return None
    return {
        "calendar": calendar.strip(),
        "title": summary.strip() or "(untitled)",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "all_day": all_day.strip().lower() == "true",
        "location": location if location != "missing value" else "",
    }


def _to_datetime(raw: str) -> datetime:
    year, month, day, hour, minute = (int(p) for p in raw.split(","))
    return datetime(year, month, day, hour, minute)


def today(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter to events starting today — the common case for a briefing."""
    now = datetime.now()
    end_of_day = now.replace(hour=23, minute=59, second=59)
    return [e for e in events if now.date() <= datetime.fromisoformat(e["start"]).date() <= end_of_day.date()]


def next_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The next event that hasn't started yet, skipping all-day entries."""
    now = datetime.now()
    upcoming_timed = [
        e for e in events
        if not e["all_day"] and datetime.fromisoformat(e["start"]) > now
    ]
    return upcoming_timed[0] if upcoming_timed else None


def describe_when(event: dict[str, Any], now: datetime | None = None) -> str:
    """Human phrasing for when an event is — 'in 40 minutes', 'tomorrow at 2pm'."""
    now = now or datetime.now()
    start = datetime.fromisoformat(event["start"])
    delta = start - now

    if event["all_day"]:
        days = (start.date() - now.date()).days
        return "today" if days == 0 else "tomorrow" if days == 1 else start.strftime("%A %-d %B")

    if timedelta() < delta < timedelta(hours=1):
        return f"in {int(delta.total_seconds() // 60)} minutes"
    if start.date() == now.date():
        return f"at {start.strftime('%-I:%M %p').lower()}"
    if (start.date() - now.date()).days == 1:
        return f"tomorrow at {start.strftime('%-I:%M %p').lower()}"
    return start.strftime("%A at %-I:%M %p").replace("AM", "am").replace("PM", "pm")
