"""Weather and advisories. Both sources are free and keyless.

Forecast comes from Open-Meteo. Advisories come from the US National Weather
Service, which is what actually carries "heat advisory" / "flood watch" style
warnings — the thing worth being told before leaving the house. NWS is US-only,
so outside the US the forecast still works and alerts come back empty rather
than erroring.
"""
from typing import Any

import requests

from config.settings import HOME_LAT, HOME_LON, TIMEZONE

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
NWS_ALERTS = "https://api.weather.gov/alerts/active"
GEOLOCATE = "http://ip-api.com/json"
# NWS asks for a contactable UA and rejects requests without one.
NWS_HEADERS = {"User-Agent": "JARVIS personal assistant (github.com/NividPathak/J.A.R.V.I.S)"}
TIMEOUT = 15

# WMO codes, condensed to what a person would actually say.
WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "severe thunderstorms",
}

_located: tuple[float, float] | None = None


def location() -> tuple[float, float]:
    """Configured coordinates, else geolocate by IP once and remember it."""
    global _located
    if HOME_LAT and HOME_LON:
        return HOME_LAT, HOME_LON
    if _located is None:
        r = requests.get(GEOLOCATE, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        if d.get("status") != "success":
            raise RuntimeError("Could not determine location; set JARVIS_LAT/JARVIS_LON")
        _located = (float(d["lat"]), float(d["lon"]))
    return _located


def forecast(lat: float | None = None, lon: float | None = None) -> dict[str, Any]:
    if lat is None or lon is None:
        lat, lon = location()
    r = requests.get(OPEN_METEO, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "hourly": "precipitation_probability,temperature_2m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
        "timezone": TIMEZONE, "forecast_days": 3,
    }, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()

    current, daily = d["current"], d["daily"]
    return {
        "now": {
            "temp": round(current["temperature_2m"]),
            "feels_like": round(current["apparent_temperature"]),
            "condition": WMO.get(current["weather_code"], "unknown"),
            "wind_mph": round(current["wind_speed_10m"]),
            "precipitation": current["precipitation"],
        },
        "days": [
            {
                "date": daily["time"][i],
                "high": round(daily["temperature_2m_max"][i]),
                "low": round(daily["temperature_2m_min"][i]),
                "rain_chance": daily["precipitation_probability_max"][i],
                "condition": WMO.get(daily["weather_code"][i], "unknown"),
            }
            for i in range(len(daily["time"]))
        ],
        "rain_next_12h": max(d["hourly"]["precipitation_probability"][:12] or [0]),
    }


def alerts(lat: float | None = None, lon: float | None = None) -> list[dict[str, Any]]:
    """Active NWS advisories. Empty outside the US rather than an error."""
    if lat is None or lon is None:
        lat, lon = location()
    r = requests.get(
        NWS_ALERTS, params={"point": f"{lat},{lon}"}, headers=NWS_HEADERS, timeout=TIMEOUT
    )
    if r.status_code == 404:  # outside NWS coverage
        return []
    r.raise_for_status()

    # NWS reissues the same advisory as separate features as it's updated, so
    # the raw list routinely contains the same event two or three times. Keep
    # the most recently issued of each.
    latest: dict[str, dict[str, Any]] = {}
    for p in (f["properties"] for f in r.json().get("features", [])):
        event = p.get("event") or "Alert"
        candidate = {
            "event": event,
            "severity": p.get("severity"),
            "urgency": p.get("urgency"),
            "headline": p.get("headline"),
            "instruction": (p.get("instruction") or "").strip()[:400],
            "sent": p.get("sent"),
            "ends": p.get("ends"),
        }
        if event not in latest or (candidate["sent"] or "") > (latest[event]["sent"] or ""):
            latest[event] = candidate
    return list(latest.values())


def advice(snapshot: dict[str, Any], alerts_: list[dict[str, Any]] | None = None) -> list[str]:
    """Concrete things to do about the weather, not just numbers.

    This is the 'cautions to take' part — the reason to be told at all. Official
    NWS advisories come first: an active air-quality or heat alert outranks
    anything inferred from the raw numbers, and dropping it in favour of "it's
    warm out" would bury the one thing worth acting on.
    """
    tips: list[str] = []
    now, days = snapshot["now"], snapshot["days"]

    for alert in alerts_ or []:
        event = alert.get("event") or "Weather alert"
        tips.append(f"{event} in effect — {_alert_action(event)}")

    # Apparent temperature can sit well below the real reading in dry air, so
    # check both: 92F actual still warrants water even when it "feels like" 81F.
    hottest = max(now["feels_like"], now["temp"])
    if hottest >= 95:
        tips.append("Dangerously hot — limit time outside and keep water on you.")
    elif hottest >= 88:
        tips.append("Hot out — worth carrying water.")
    elif now["feels_like"] <= 32:
        tips.append("Freezing — layers and gloves.")
    elif now["feels_like"] <= 45:
        tips.append("Cold enough for a proper jacket.")

    if snapshot["rain_next_12h"] >= 60:
        tips.append("Rain likely in the next few hours — take an umbrella.")
    elif snapshot["rain_next_12h"] >= 30:
        tips.append("Rain is possible later — an umbrella wouldn't hurt.")

    if now["wind_mph"] >= 25:
        tips.append(f"Windy — {now['wind_mph']}mph.")
    if days and days[0]["high"] - days[0]["low"] >= 25:
        tips.append("Big temperature swing today — dress in layers.")

    # Worth a heads-up the day before, not just on the morning of.
    if len(days) > 1 and days[1]["rain_chance"] >= 70:
        tips.append(f"Tomorrow looks wet — {days[1]['rain_chance']}% chance of rain.")
    return tips


def _alert_action(event: str) -> str:
    """What an advisory actually means for the day."""
    e = event.lower()
    if "air quality" in e:
        return "limit strenuous activity outdoors, especially if you're sensitive to it."
    if "heat" in e:
        return "stay hydrated and out of direct sun in the afternoon."
    if "flood" in e:
        return "avoid low-lying roads and underpasses."
    if any(w in e for w in ("thunder", "storm", "tornado")):
        return "stay indoors while it passes and keep away from windows."
    if "wind" in e:
        return "secure anything loose outside; driving may be difficult."
    if any(w in e for w in ("snow", "ice", "winter", "freeze")):
        return "allow extra travel time and expect slick surfaces."
    return "check the details before heading out."
