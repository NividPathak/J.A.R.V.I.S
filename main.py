#!/usr/bin/env python3
"""J.A.R.V.I.S — orchestrator entrypoint.

    python main.py                      # interactive
    python main.py "what's my day look like"
    python main.py --explain "brief me"  # show the routing decision

Text for now; Phase 6 puts speech in front of exactly this loop.
"""
import argparse
import logging
import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from agents.calendar_agent import CalendarAgent
from agents.news_agent import NewsAgent
from agents.weather_agent import WeatherAgent
from config.settings import JARVIS_NAME, JARVIS_USER
from core.llm import get_llm
from core.orchestrator import Orchestrator, Response
from core.router.llm_router import LLMRouter

console = Console()


def build(provider: str | None = None, model: str | None = None) -> Orchestrator:
    llm = get_llm(provider=provider, model=model)
    agents = {a.name: a for a in (CalendarAgent(llm=llm), WeatherAgent(llm=llm), NewsAgent(llm=llm))}
    return Orchestrator(LLMRouter(llm), agents)


def show(response: Response, explain: bool = False) -> None:
    if explain:
        route = response.route
        detail = (
            f"[bold]route[/]      {route}\n"
            f"[bold]agents[/]     {', '.join(route.agents) or '(handled directly)'}\n"
            f"[bold]elapsed[/]    {response.elapsed * 1000:.0f}ms"
        )
        if response.replies:
            per = "  ".join(f"{r.agent}={r.elapsed * 1000:.0f}ms" for r in response.replies)
            detail += f"\n[bold]per agent[/]  {per}"
            if response.parallel_saving > 0:
                detail += f"\n[bold]saved[/]      {response.parallel_saving * 1000:.0f}ms by running in parallel"
        console.print(Panel(detail, border_style="dim", title="routing", title_align="left"))

    # Escape: agent output is content, not markup. Headlines and scores routinely
    # contain brackets, which Rich would otherwise swallow as style tags.
    console.print(
        Panel(escape(response.text), border_style="cyan", title=JARVIS_NAME, title_align="left")
    )


def repl(orchestrator: Orchestrator, explain: bool) -> int:
    console.print(f"[dim]{JARVIS_NAME} online. Ctrl-C to exit.[/]\n")
    while True:
        try:
            utterance = console.input(f"[bold yellow]{JARVIS_USER}[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye, sir.[/]")
            return 0
        if not utterance:
            continue
        if utterance in {"/exit", "/quit"}:
            return 0
        show(orchestrator.handle(utterance), explain)


def main() -> int:
    ap = argparse.ArgumentParser(description="J.A.R.V.I.S")
    ap.add_argument("utterance", nargs="*", help="one-shot request; omit for interactive")
    ap.add_argument("-e", "--explain", action="store_true", help="show the routing decision")
    ap.add_argument("--provider", help="ollama | anthropic")
    ap.add_argument("--model", help="override model id")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    orchestrator = build(args.provider, args.model)
    if args.utterance:
        show(orchestrator.handle(" ".join(args.utterance)), args.explain)
        return 0
    return repl(orchestrator, args.explain)


if __name__ == "__main__":
    sys.exit(main())
