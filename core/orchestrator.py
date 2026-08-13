"""The orchestrator: route, dispatch, compose.

Agents run in parallel. That's the whole architectural argument for subagents
here — a morning briefing needs calendar, weather and news at once, and serially
that's the sum of three round trips instead of the slowest one.

The four outcomes are handled distinctly on purpose:

  dispatch    confident, and at least one agent owns it
  self        smalltalk or a meta command — answered here, no agent
  rejection   confidently out of scope: "that's not something I do"
  unsure      below the confidence floor: ask, don't guess

That last split is the reason `Route` carries confidence at all. Misrouting is
worse than a clarifying question once the input is voice, and "I don't do that"
is a better answer than "sorry, say again?" when the request was heard perfectly
well.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from agents.base import Agent, AgentReply
from core.router.base import Intent, Route, Router

log = logging.getLogger("jarvis.orchestrator")


@dataclass
class Response:
    text: str
    route: Route
    replies: list[AgentReply] = field(default_factory=list)
    #: Wall-clock for the whole turn, routing included.
    elapsed: float = 0.0

    @property
    def parallel_saving(self) -> float:
        """Seconds saved by fanning out rather than running agents in sequence."""
        if len(self.replies) < 2:
            return 0.0
        return sum(r.elapsed for r in self.replies) - max(r.elapsed for r in self.replies)


class Orchestrator:
    def __init__(self, router: Router, agents: dict[str, Agent]):
        self.router = router
        self.agents = agents

    def handle(self, utterance: str, route: Route | None = None) -> Response:
        """Answer one request.

        `route` lets a caller that has already routed — the voice loop inspects
        the route to decide whether the briefing fast path applies — hand it in
        rather than paying for a second identical classification.
        """
        started = time.perf_counter()
        route = route or self.router.route(utterance)
        log.info("routed %r -> %s", utterance[:60], route)

        if route.should_dispatch:
            replies = self._dispatch(route.agents, utterance)
            text = self._compose(replies)
        elif route.self_handled:
            replies, text = [], self._self_handle(route, utterance)
        elif route.is_rejection:
            replies, text = [], (
                "That's outside what I handle — I cover your calendar, weather, "
                "news and sport."
            )
        else:
            replies, text = [], "I didn't catch that. Could you rephrase?"

        return Response(
            text=text,
            route=route,
            replies=replies,
            elapsed=time.perf_counter() - started,
        )

    def _dispatch(self, names: list[str], utterance: str) -> list[AgentReply]:
        """Fan out to every agent at once, preserving route order in the result."""
        targets = [n for n in names if n in self.agents]
        for missing in set(names) - set(targets):
            log.warning("no agent registered for %r", missing)
        if not targets:
            return []

        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            return list(pool.map(lambda n: self._run_one(n, utterance), targets))

    def _run_one(self, name: str, utterance: str) -> AgentReply:
        agent, started = self.agents[name], time.perf_counter()
        try:
            text, ok = agent.handle(utterance), True
        except Exception as e:
            log.warning("agent %s failed: %s", name, e)
            text, ok = f"({name} is unavailable right now)", False
        return AgentReply(agent=name, text=text, ok=ok, elapsed=time.perf_counter() - started)

    @staticmethod
    def _compose(replies: list[AgentReply]) -> str:
        """Join agent replies.

        Multiple replies get labelled headings rather than being run together.
        Each specialist answers from its own data, so an unlabelled concatenation
        reads as one voice contradicting itself — and there's no cheap way to
        synthesise a single answer without a further model call on top of the
        slowest agent.
        """
        if not replies:
            return "I couldn't reach anything that handles that."
        usable = [r for r in replies if r.ok] or replies
        if len(usable) == 1:
            return usable[0].text
        return "\n\n".join(f"{r.agent.title()} — {r.text}" for r in usable)

    def _self_handle(self, route: Route, utterance: str) -> str:
        if Intent.SYSTEM in route.intents:
            listed = "\n".join(f"  · {a.description}" for a in self.agents.values())
            return f"I can help with:\n{listed}"
        return "At your service, sir."
