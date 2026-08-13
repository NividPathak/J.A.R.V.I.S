#!/usr/bin/env python3
"""Live dashboard — reads the cache, fetches nothing.

    python dashboard/server.py            # http://localhost:8765
    python dashboard/server.py --port 9000

The poller is still the only thing that talks to upstreams. This server is a
reader like the agents are, so opening the page in ten tabs costs nothing and
cannot blow a rate limit.

stdlib http.server rather than FastAPI: it's a localhost read-only page over a
SQLite file, and the dependency would buy nothing.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agents.news_agent import SPORT_LABELS, SPORT_SOURCES  # noqa: E402
from data.cache import Cache  # noqa: E402

STATIC = Path(__file__).parent
DEFAULT_PORT = 8765


def health(entry) -> str:
    """One of ok / stale / failing / empty. Paired with a text label in the UI —
    the status colour never carries the meaning by itself."""
    if entry is None or entry.payload is None:
        return "empty"
    if not entry.is_healthy:
        return "failing"
    return "stale" if entry.is_stale else "ok"


def build_state(cache: Cache) -> dict:
    entries = {e.source: e for e in cache.all()}

    sports = []
    for key in SPORT_SOURCES:
        entry = entries.get(key)
        payload = (entry.payload if entry else None) or {}
        events = payload.get("events") or payload.get("games") or []
        sports.append({
            "key": key,
            "label": SPORT_LABELS.get(key, key.upper()),
            "events": events,
            "live": bool(payload.get("live")),
            "standings": payload.get("standings"),
            # F1 carries a classified result rather than a scoreline, so its
            # panel is driven by these instead of the event list.
            "last_race": payload.get("last_race"),
            "race_control": payload.get("race_control"),
            "health": health(entry),
            "age_seconds": int(entry.age) if entry and entry.age is not None else None,
            "error": entry.last_error if entry else None,
        })

    weather_entry = entries.get("weather")
    weather = (weather_entry.payload if weather_entry else None) or {}
    calendar_entry = entries.get("calendar")
    calendar = (calendar_entry.payload if calendar_entry else None) or {}

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sports": sports,
        "weather": {
            "temp": (weather.get("now") or {}).get("temp"),
            "condition": (weather.get("now") or {}).get("condition"),
            "alerts": [a.get("event") for a in weather.get("alerts") or []],
            "health": health(weather_entry),
        },
        "calendar": {
            "next": calendar.get("next"),
            "today_count": len(calendar.get("today") or []),
            "health": health(calendar_entry),
        },
    }


class Handler(SimpleHTTPRequestHandler):
    cache: Cache

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def do_GET(self):  # noqa: N802 — stdlib naming
        if self.path.split("?")[0] not in ("/api/state", "/api/state/"):
            return super().do_GET()
        try:
            body = json.dumps(build_state(self.cache)).encode()
            self.send_response(200)
        except Exception as e:  # a broken cache read shouldn't 500 the page silently
            body = json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet — one poll every 15s per tab is noise
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="JARVIS dashboard")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1", help="localhost only by default")
    args = ap.parse_args()

    Handler.cache = Cache()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard on http://{args.host}:{args.port}  (Ctrl-C to stop)")
    if not any(e.payload for e in Handler.cache.all()):
        print("Cache is empty — run: python poll.py once -f")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
