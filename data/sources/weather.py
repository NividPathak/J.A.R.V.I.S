"""Weather source — forecast plus active advisories.

Polls faster while an advisory is live. A heat or storm warning is the one
weather situation where being 15 minutes stale actually matters.
"""
from typing import Any

from config.settings import TIMEZONE
from data.cache import Entry
from data.sources.base import Source
from integrations import weather

CALM_INTERVAL = 900.0  # 15 min
ALERT_INTERVAL = 300.0  # 5 min while something is active


class WeatherSource(Source):
    name = "weather"
    ttl = CALM_INTERVAL
    daily_budget = None

    def fetch(self) -> dict[str, Any]:
        here = weather.location()
        snapshot = weather.forecast(here.lat, here.lon)
        # Alerts are US-only and return [] elsewhere, so a failure here is real
        # and worth surfacing rather than swallowing.
        snapshot["alerts"] = weather.alerts(here.lat, here.lon)
        snapshot["advice"] = weather.advice(snapshot, snapshot["alerts"])
        snapshot["location"] = {
            "lat": here.lat,
            "lon": here.lon,
            "source": here.source,
            "place": here.place,
            "detected_tz": here.detected_tz,
        }
        # A guessed location and a configured timezone that disagree is always a
        # misconfiguration — it means the coordinates are wrong, the clock is
        # wrong, or both.
        if here.is_guess and here.detected_tz and here.detected_tz != TIMEZONE:
            snapshot["location"]["tz_mismatch"] = f"{here.detected_tz} vs configured {TIMEZONE}"
        return snapshot

    def interval(self, last: Entry | None) -> float:
        if last and last.payload and last.payload.get("alerts"):
            return ALERT_INTERVAL
        return CALM_INTERVAL
