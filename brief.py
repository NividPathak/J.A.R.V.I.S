#!/usr/bin/env python3
"""Morning briefing.

    python brief.py                  # print it
    python brief.py --speak          # read it aloud
    python brief.py --notify         # macOS notification
    python brief.py --speak --notify # what the 7am schedule runs

Composes from cache in milliseconds, so it works with Ollama down and can be
run as often as you like.
"""
import argparse
import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from agents.calendar_agent import CalendarAgent
from agents.news_agent import NewsAgent
from agents.weather_agent import WeatherAgent
from core.briefing import BriefingComposer
from integrations import macos

console = Console()


def build() -> BriefingComposer:
    # No LLM needed — every section is templated.
    agents = {a.name: a for a in (CalendarAgent(), WeatherAgent(), NewsAgent())}
    return BriefingComposer(agents)


def main() -> int:
    ap = argparse.ArgumentParser(description="J.A.R.V.I.S morning briefing")
    ap.add_argument("-s", "--speak", action="store_true", help="read aloud")
    ap.add_argument("-n", "--notify", action="store_true", help="macOS notification")
    ap.add_argument("-q", "--quiet", action="store_true", help="suppress terminal output")
    ap.add_argument("--speech-text", action="store_true", help="print the spoken form and exit")
    args = ap.parse_args()

    briefing = build().compose()

    if args.speech_text:
        print(briefing.as_speech())
        return 0

    if not args.quiet:
        console.print(
            Panel(
                escape(briefing.as_text()),
                border_style="cyan",
                title="Briefing",
                subtitle=f"composed in {briefing.elapsed * 1000:.0f}ms",
                title_align="left",
            )
        )

    if args.notify:
        title, body = briefing.as_notification()
        macos.notify(title, body)
    if args.speak:
        macos.speak(briefing.as_speech())
    return 0


if __name__ == "__main__":
    sys.exit(main())
