#!/usr/bin/env python3
"""Data-layer CLI — run the poller, force a refresh, or inspect the cache.

    python poll.py status      # what's cached, how old, what's broken
    python poll.py once        # one pass over anything that's due
    python poll.py once -f     # force-refresh everything, ignoring intervals
    python poll.py run         # the daemon
"""
import argparse
import logging
import sys
import time

from rich.console import Console
from rich.table import Table

from data.cache import Cache
from data.poller import Poller
from data.sources import sports
from data.sources.calendar import CalendarSource
from data.sources.nba import NBASource
from data.sources.news import NewsSource
from data.sources.weather import WeatherSource

console = Console()

SOURCES = [
    CalendarSource(),
    WeatherSource(),
    NewsSource(),
    NBASource(),
    sports.nfl(),
    sports.f1_source(),
    sports.cricket(),
]


def _duration(seconds: float) -> str:
    """Format a span of seconds compactly: 90 -> '2m', 7200 -> '2h'."""
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds / size:.0f}{unit}"
    return f"{seconds:.0f}s"


def _age(seconds: float | None) -> str:
    return "never" if seconds is None else f"{_duration(seconds)} ago"


def cmd_status(_args) -> int:
    cache = Cache()
    entries = {e.source: e for e in cache.all()}

    table = Table(title="JARVIS data layer", header_style="bold cyan")
    for col in ("Source", "State", "Fetched", "Next poll", "Detail"):
        table.add_column(col)

    for source in SOURCES:
        entry = entries.get(source.name)
        if entry is None:
            table.add_row(source.name, "[dim]empty[/]", "never", "now", "not yet polled")
            continue

        if not entry.is_healthy:
            state = "[red]failing[/]"
        elif entry.is_stale:
            state = "[yellow]stale[/]"
        else:
            state = "[green]ok[/]"

        due_in = (entry.fetched_at + source.interval(entry) - time.time()) if entry.fetched_at else 0
        if entry.last_error:
            detail = entry.last_error
        elif isinstance(entry.payload, dict):
            detail = ", ".join(entry.payload)
        else:
            detail = type(entry.payload).__name__
        table.add_row(
            source.name,
            state,
            _age(entry.age),
            "due" if due_in <= 0 else f"in {_duration(due_in)}",
            detail,
        )

    console.print(table)
    for extra in set(entries) - {s.name for s in SOURCES}:
        console.print(f"[dim]orphaned cache entry: {extra}[/]")
    return 0


def cmd_once(args) -> int:
    results = Poller(SOURCES).tick(force=args.force)
    if not results:
        console.print("[dim]Nothing due. Use -f to force.[/]")
        return 0
    for name, ok in results.items():
        console.print(f"  {'[green]ok[/]' if ok else '[red]failed[/]'}  {name}")
    return 0 if all(results.values()) else 1


def cmd_run(_args) -> int:
    try:
        Poller(SOURCES).run()
    except KeyboardInterrupt:
        console.print("\n[dim]Poller stopped.[/]")
    return 0


def main() -> int:
    # Shared flags live on a parent so they work after the subcommand, git-style.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true")

    parser = argparse.ArgumentParser(description="JARVIS data layer")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common], help="show cache state").set_defaults(fn=cmd_status)
    once = sub.add_parser("once", parents=[common], help="poll anything due, then exit")
    once.add_argument("-f", "--force", action="store_true", help="ignore intervals")
    once.set_defaults(fn=cmd_once)
    sub.add_parser("run", parents=[common], help="poll continuously").set_defaults(fn=cmd_run)

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
