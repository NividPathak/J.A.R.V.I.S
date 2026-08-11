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
