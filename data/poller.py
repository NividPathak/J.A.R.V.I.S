"""The single writer.

Every upstream call in the system goes through here. Nothing else fetches, so
the interval on each Source *is* the rate limit — there's no second code path
that can quietly blow the budget.
"""
import logging
import time
from typing import Sequence

from data.cache import Cache
from data.sources.base import Source

log = logging.getLogger("jarvis.poller")


class Poller:
    def __init__(self, sources: Sequence[Source], cache: Cache | None = None):
        self.sources = list(sources)
        self.cache = cache or Cache()
        for warning in filter(None, (s.validate_budget() for s in self.sources)):
            log.warning(warning)

    def due(self, source: Source) -> bool:
        entry = self.cache.get(source.name)
        if entry is None or entry.fetched_at is None:
            return True
        return time.time() - entry.fetched_at >= source.interval(entry)

    def refresh(self, source: Source) -> bool:
        """Fetch one source. Returns True on success.

        A failure is recorded but never overwrites the last good payload — a
        broken upstream degrades one tile instead of blanking it.
        """
        try:
            payload = source.fetch()
        except Exception as e:
            log.warning("%s fetch failed: %s", source.name, e)
            self.cache.record_failure(source.name, f"{type(e).__name__}: {e}", source.ttl)
            return False

        self.cache.put(source.name, payload, source.ttl)
        log.info("%s refreshed", source.name)
        return True

    def tick(self, force: bool = False) -> dict[str, bool]:
        """One pass over every source. Returns {name: succeeded} for those polled."""
        return {
            s.name: self.refresh(s)
            for s in self.sources
            if force or self.due(s)
        }

    def sleep_seconds(self, floor: float = 5.0, ceiling: float = 300.0) -> float:
        """How long until the next source comes due — so the loop idles instead of spinning."""
        now = time.time()
        waits = []
        for s in self.sources:
            entry = self.cache.get(s.name)
            if entry is None or entry.fetched_at is None:
                return floor
            waits.append(entry.fetched_at + s.interval(entry) - now)
        return max(floor, min(ceiling, min(waits, default=ceiling)))

    def run(self) -> None:
        """Poll forever. This is the process the briefing and dashboard sit on top of."""
        log.info("poller starting with %d sources", len(self.sources))
        while True:
            self.tick()
            time.sleep(self.sleep_seconds())
