"""Weather agent — forecast and the advisories worth acting on."""
from agents.base import CachedAgent


class WeatherAgent(CachedAgent):
    name = "weather"
    description = "weather and advisories — rain, heat, what to wear"
    sources = ("weather",)

    def context(self) -> str:
        entry = self._cache.get("weather")
        if entry is None or not entry.payload:
            return ""

        p = entry.payload
        now = p["now"]
        lines = [self._staleness_note()]

        # Advisories go first — buried at the bottom the model skipped them in
        # favour of the temperature, which is the wrong thing to lead with.
        #
        # Written as plain sentences rather than under a heading: told not to
        # echo headings, the model echoed them anyway ("URGENT — ACTIVE
        # ADVISORIES:" appeared verbatim in its reply). Removing the heading is
        # structural, so compliance stops mattering. Prefer this over another
        # instruction whenever the scaffolding can simply be deleted.
        for alert in p.get("alerts") or []:
            sentence = f"There is an active {alert['event']}."
            if alert.get("headline"):
                sentence += f" {alert['headline']}."
            if alert.get("instruction"):
                sentence += f" Official guidance: {alert['instruction'][:200]}"
            lines.append(sentence)
        if p.get("alerts"):
            lines.append("")

        lines += [
            f"Right now it is {now['temp']}F, feels like {now['feels_like']}F, "
            f"{now['condition']}, wind {now['wind_mph']}mph.",
            f"There is a {p['rain_next_12h']}% chance of rain in the next 12 hours.",
            "",
        ]

        for day in p.get("days", []):
            lines.append(
                f"On {day['date']} the low is {day['low']}F and the high {day['high']}F, "
                f"{day['condition']}, with a {day['rain_chance']}% chance of rain."
            )

        if p.get("advice"):
            lines.append("")
            lines.extend(f"Worth mentioning: {tip}" for tip in p["advice"])
        return "\n".join(lines)

    def brief(self) -> str:
        entry = self._cache.get("weather")
        if entry is None or not entry.payload:
            return "Weather is unavailable."

        p = entry.payload
        now, days = p["now"], p.get("days") or []
        loc = p.get("location") or {}
        lines: list[str] = []

        # Name the place whenever it was guessed. IP geolocation resolves the
        # network, not the person — this reported Boulder for a machine on a
        # university network and read as a perfectly ordinary forecast.
        if loc.get("source") == "ip" and loc.get("place"):
            lines.append(f"Weather for {loc['place']} (location guessed from your network).")

        # Advisories next — the whole point of a briefing is being told the
        # thing you'd want to know before leaving the house.
        for alert in p.get("alerts") or []:
            lines.append(f"{alert['event']} in effect.")

        line = f"{now['temp']} degrees, {now['condition']}"
        if days:
            line += f", high of {days[0]['high']} and low of {days[0]['low']}"
        lines.append(line + ".")

        if p["rain_next_12h"] >= 30:
            lines.append(f"{p['rain_next_12h']}% chance of rain in the next twelve hours.")

        # Skip the first tip when it merely restates the alert named above.
        tips = [t for t in (p.get("advice") or []) if not t.startswith(tuple(
            (a.get("event") or "") for a in (p.get("alerts") or [])
        ) or ("\0",))]
        lines.extend(tips[:2])
        return "\n".join(lines)

    def summary(self) -> str:
        entry = self._cache.get("weather")
        if entry is None or not entry.payload:
            return "Weather unavailable."

        p = entry.payload
        now, days = p["now"], p.get("days") or []
        line = f"{now['temp']}F and {now['condition']}"
        if days:
            line += f", high of {days[0]['high']}"
        line += "."

        # Lead with the advisory when there is one — it's the actionable part.
        if p.get("advice"):
            return f"{line} {p['advice'][0]}"
        return line
