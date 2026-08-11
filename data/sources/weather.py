"""Weather source — forecast plus active advisories.

Polls faster while an advisory is live. A heat or storm warning is the one
weather situation where being 15 minutes stale actually matters.
"""
from typing import Any

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
        lat, lon = weather.location()
        snapshot = weather.forecast(lat, lon)
        # Alerts are US-only and return [] elsewhere, so a failure here is real
        # and worth surfacing rather than swallowing.
        snapshot["alerts"] = weather.alerts(lat, lon)
        snapshot["advice"] = weather.advice(snapshot, snapshot["alerts"])
        snapshot["location"] = {"lat": lat, "lon": lon}
        return snapshot

    def interval(self, last: Entry | None) -> float:
        if last and last.payload and last.payload.get("alerts"):
            return ALERT_INTERVAL
        return CALM_INTERVAL
