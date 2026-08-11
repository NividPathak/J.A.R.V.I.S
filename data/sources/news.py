"""Headlines source."""
from typing import Any

from data.cache import Entry
from data.sources.base import Source
from integrations import news

INTERVAL = 1800.0  # 30 min — faster than the news cycle actually turns over


class NewsSource(Source):
    name = "news"
    ttl = INTERVAL
    daily_budget = None

    def fetch(self) -> dict[str, Any]:
        headlines = news.fetch_all()
        return {
            "headlines": headlines,
            "by_topic": {
                topic: [h for h in headlines if h["topic"] == topic]
                for topic in sorted({h["topic"] for h in headlines})
            },
        }

    def interval(self, last: Entry | None) -> float:
        return INTERVAL
