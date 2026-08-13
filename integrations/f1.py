"""Formula 1 detail — two sources, because no single free one has it all.

Jolpica (the Ergast successor) has classified results: starting grid, finishing
order, fastest lap, and a per-driver status that distinguishes a retirement from
a collision. OpenF1 has race control, which is the only free place flags and
incident messages appear.

Both are volunteer/community run and rate limited (Jolpica: 200/hour
unauthenticated), which is exactly why this sits behind the poller like
everything else.
"""
import logging
from typing import Any

import requests

log = logging.getLogger("jarvis.f1")

JOLPICA = "https://api.jolpi.ca/ergast/f1"
OPENF1 = "https://api.openf1.org/v1"
TIMEOUT = 20

#: Statuses that mean the car stopped, as opposed to finishing a lap down.
RETIREMENT_HINTS = ("accident", "collision", "spun", "engine", "gearbox", "hydraulics",
                    "power unit", "brakes", "suspension", "retired", "withdrew",
                    "disqualified", "puncture", "electrical", "overheating")


def last_race() -> dict[str, Any] | None:
    """Classified result of the most recent completed race."""
    r = requests.get(f"{JOLPICA}/current/last/results.json", timeout=TIMEOUT)
    r.raise_for_status()
    races = r.json()["MRData"]["RaceTable"]["Races"]
    if not races:
        return None

    race = races[0]
    results = [_result(x) for x in race.get("Results", [])]
    fastest = min(
        (r for r in results if r["fastest_lap"]),
        key=lambda r: r["fastest_lap"], default=None,
    )
    return {
        "name": race.get("raceName"),
        "round": race.get("round"),
        "season": race.get("season"),
        "date": race.get("date"),
        "circuit": (race.get("Circuit") or {}).get("circuitName"),
        "locality": ((race.get("Circuit") or {}).get("Location") or {}).get("locality"),
        "results": results,
        "podium": results[:3],
        "fastest_lap": fastest,
        "top_speed": _top_speed(results),
        "retirements": [r for r in results if r["retired"]],
        "biggest_gainer": _biggest_gainer(results),
    }


def _result(raw: dict) -> dict[str, Any]:
    driver = raw.get("Driver") or {}
    lap = raw.get("FastestLap") or {}
    status = raw.get("status") or ""
    grid, pos = _int(raw.get("grid")), _int(raw.get("position"))
    return {
        "position": pos,
        "grid": grid,
        "gained": (grid - pos) if grid and pos else None,
        "driver": f"{driver.get('givenName','')} {driver.get('familyName','')}".strip(),
        "code": driver.get("code") or (driver.get("familyName") or "")[:3].upper(),
        "constructor": (raw.get("Constructor") or {}).get("name"),
        "laps": _int(raw.get("laps")),
        "points": raw.get("points"),
        "status": status,
        # "+1 Lap" is a finish, not a retirement; only real stoppages count.
        "retired": any(h in status.lower() for h in RETIREMENT_HINTS),
        "fastest_lap": (lap.get("Time") or {}).get("time"),
        "fastest_lap_speed": (lap.get("AverageSpeed") or {}).get("speed"),
    }


def _top_speed(results: list[dict]) -> dict[str, Any] | None:
    """Jolpica reports average speed on the fastest lap, and often omits it."""
    with_speed = [r for r in results if r.get("fastest_lap_speed")]
    if not with_speed:
        return None
    best = max(with_speed, key=lambda r: float(r["fastest_lap_speed"]))
    return {"driver": best["driver"], "speed": best["fastest_lap_speed"], "units": "km/h"}


def _biggest_gainer(results: list[dict]) -> dict[str, Any] | None:
    gains = [r for r in results if r.get("gained") and r["gained"] > 0]
    return max(gains, key=lambda r: r["gained"]) if gains else None


def race_control(year: int | None = None) -> list[dict[str, Any]]:
    """Flags and incident messages from the latest completed race.

    OpenF1 only — nothing else free carries this. Returns [] rather than raising
    when unavailable, since the race result is still worth showing without it.
    """
    from datetime import date

    year = year or date.today().year
    try:
        sessions = requests.get(
            f"{OPENF1}/sessions", params={"session_name": "Race", "year": year}, timeout=TIMEOUT
        ).json()
        today = str(date.today())
        past = [s for s in sessions if (s.get("date_start") or "")[:10] <= today]
        if not past:
            return []
        session = max(past, key=lambda s: s["date_start"])

        messages = requests.get(
            f"{OPENF1}/race_control", params={"session_key": session["session_key"]}, timeout=TIMEOUT
        ).json()
    except Exception as e:
        log.warning("race control unavailable: %s", e)
        return []

    events = []
    for m in messages:
        flag = (m.get("flag") or "").upper()
        text = (m.get("message") or "").strip()
        # Blue flags are routine lapping traffic — dozens per race, no signal.
        if not flag or flag in ("CLEAR", "BLUE"):
            continue
        events.append({
            "lap": m.get("lap_number"),
            "flag": flag,
            "message": text,
            "scope": m.get("scope"),
        })
    return events


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
