"""The morning briefing.

Assembled entirely from templated `brief()` calls, so it costs a few
milliseconds, is deterministic, and still works when Ollama is down. That
matters more here than anywhere else in the system: this fires unattended at
dawn, and a briefing that intermittently fails is one you stop trusting and then
stop reading.

Three renderings, because the constraints genuinely differ. The terminal can
take structure. Speech cannot — bullets and abbreviations read badly aloud.
A notification gets a couple of lines before macOS truncates it, so it carries
only what would make you go and read the rest.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from agents.base import Agent
from config.settings import JARVIS_USER
from data.cache import Cache

#: Beyond this, data is old enough that the briefing should admit it.
STALE_AFTER = 3600.0


@dataclass
class Section:
    agent: str
    text: str
    ok: bool = True


@dataclass
class Briefing:
    greeting: str
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    elapsed: float = 0.0

    def as_text(self) -> str:
        parts = [self.greeting] + [s.text.strip() for s in self.sections if s.text.strip()]
        if self.warnings:
            parts.append("— " + "; ".join(self.warnings))
        return "\n\n".join(parts)

    def as_speech(self) -> str:
        """Flatten to something that reads well aloud.

        Section headings, list punctuation and source attributions all exist for
        the eye. Spoken, they land as "Sport colon, N B A colon" — so they're
        stripped rather than transliterated.
        """
        spoken = "\n".join(
            s.text for s in self.sections if s.ok and s.text.strip()
        )
        spoken = f"{self.greeting}\n{spoken}"

        spoken = re.sub(r"^\s*(Sport|Headlines):\s*$", "", spoken, flags=re.M)
        spoken = re.sub(r"^\s*[-•]\s*", "", spoken, flags=re.M)
        spoken = re.sub(r"\s*\(([A-Z][A-Za-z .]{1,18})\)\s*$", "", spoken, flags=re.M)
        spoken = re.sub(r"\s*\(([^)]{1,30})\)", r", \1", spoken)
        spoken = spoken.replace("%", " percent").replace(" — ", ", ")

        # One sentence per line, so the speech engine paces it properly.
        lines = [ln.strip().rstrip(".") for ln in spoken.split("\n") if ln.strip()]
        spoken = ". ".join(lines) + "."
        spoken = re.sub(r"\s{2,}", " ", spoken)
        return re.sub(r"([.,])[\s,.]*\1+", r"\1", spoken)

    def as_notification(self) -> tuple[str, str]:
        """Title and a short body — macOS truncates hard, so lead with the hook."""
        headline = next(
            (s.text.split("\n")[0] for s in self.sections if s.agent == "weather" and s.ok),
            "",
        )
        calendar = next(
            (s.text.split("\n")[0] for s in self.sections if s.agent == "calendar" and s.ok),
            "",
        )
        body = " ".join(x for x in (headline, calendar) if x)[:180]
        return self.greeting, body


class BriefingComposer:
    def __init__(self, agents: dict[str, Agent], cache: Cache | None = None):
        self.agents = agents
        self.cache = cache or Cache()

    def compose(self, order: tuple[str, ...] = ("weather", "calendar", "news")) -> Briefing:
        """Assemble the briefing. Ordered by what you'd act on first."""
        started = time.perf_counter()
        targets = [self.agents[n] for n in order if n in self.agents]

        with ThreadPoolExecutor(max_workers=max(len(targets), 1)) as pool:
            sections = list(pool.map(self._section, targets))

        return Briefing(
            greeting=self._greeting(),
            sections=sections,
            warnings=self._warnings(),
            elapsed=time.perf_counter() - started,
        )

    @staticmethod
    def _section(agent: Agent) -> Section:
        try:
            return Section(agent=agent.name, text=agent.brief())
        except Exception as e:
            return Section(agent=agent.name, text=f"({agent.name} unavailable)", ok=False)

    @staticmethod
    def _greeting(now: datetime | None = None) -> str:
        now = now or datetime.now()
        hour = now.hour
        part = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
        clock = now.strftime("%-I:%M %p").lower()  # only the meridiem lowercases well
        return f"{part}, {JARVIS_USER}. It's {now.strftime('%A %-d %B')}, {clock}."

    def _warnings(self) -> list[str]:
        """Flag data old enough that the briefing shouldn't be trusted whole.

        Silence about stale data is the failure mode that matters: a briefing
        confidently reporting yesterday's weather is worse than one admitting it
        couldn't reach the forecast.

        Collapsed rather than listed per source — when the poller stops, every
        source goes stale together, and seven near-identical lines bury the
        point instead of making it.
        """
        missing, stale = [], []
        for entry in self.cache.all():
            if entry.payload is None:
                missing.append(entry.source)
            elif (entry.age or 0) > STALE_AFTER:
                stale.append((entry.source, entry.age or 0))

        warnings = []

        # A guessed location, and a timezone that disagrees with it, are both
        # silent-wrong-answer conditions rather than outages — worth saying out
        # loud precisely because nothing else looks broken.
        weather = self.cache.get("weather")
        loc = (weather.payload or {}).get("location", {}) if weather else {}
        if loc.get("tz_mismatch"):
            warnings.append(f"location/timezone mismatch ({loc['tz_mismatch']}) — set JARVIS_LAT/LON")
        elif loc.get("source") == "ip" and loc.get("place"):
            warnings.append(f"weather is for {loc['place']}, guessed from your network")
        if missing:
            warnings.append(f"no data for {', '.join(sorted(missing))}")
        if stale:
            oldest = max(age for _, age in stale)
            if len(stale) >= 3:
                warnings.append(f"data is up to {int(oldest / 3600)}h old — is the poller running?")
            else:
                warnings.append(
                    ", ".join(f"{name} is {int(age / 3600)}h old" for name, age in sorted(stale))
                )
        return warnings
