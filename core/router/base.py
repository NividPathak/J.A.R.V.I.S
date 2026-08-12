"""The routing contract.

Two decisions here shape everything downstream.

**Intents are finer-grained than agents.** The router predicts an *intent*;
a mapping turns intents into the agent that handles them. Today SPORTS and NEWS
both route to one news agent, exactly as specified. If sports later earns its own
agent, that's a one-line change to AGENT_FOR — the labelled dataset stays valid.
Labelling at agent granularity would mean re-labelling everything to split one.

**Routing is multi-label.** "What does my day look like" legitimately needs
calendar, weather and news at once — that request *is* the morning briefing.
Most utterances resolve to exactly one intent, but the set is the honest shape,
and a fine-tuned model handles multi-label fine.

The `Router` protocol is deliberately narrow so the Phase 4 fine-tuned model
drops in behind it without touching a caller.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class Intent(str, Enum):
    CALENDAR = "calendar"   # meetings, scheduling, availability
    WEATHER = "weather"     # forecast, advisories, what to wear
    SPORTS = "sports"       # scores, standings, fixtures
    NEWS = "news"           # headlines, current events
    SMALLTALK = "smalltalk"  # greetings, banter — orchestrator answers directly
    SYSTEM = "system"       # meta: capabilities, repeat, stop, cancel

    def __str__(self) -> str:
        return self.value


#: Which agent serves each intent. None = the orchestrator handles it itself.
AGENT_FOR: dict[Intent, str | None] = {
    Intent.CALENDAR: "calendar",
    Intent.WEATHER: "weather",
    Intent.SPORTS: "news",
    Intent.NEWS: "news",
    Intent.SMALLTALK: None,
    Intent.SYSTEM: None,
}

#: Below this, the orchestrator asks rather than guesses. Misrouting is much
#: worse than a clarifying question once input is voice.
CONFIDENCE_FLOOR = 0.55

#: The fine-tuned router's prompt. Defined here so `training/prepare_data.py`
#: and `TunedRouter` import the same string — if the training and inference
#: prompts drift apart, accuracy degrades silently and no test catches it.
TUNED_SYSTEM = (
    "Classify the request into labels: calendar, weather, sports, news, "
    "smalltalk, system. Reply with a comma-separated list, or none."
)


@dataclass(frozen=True)
class Route:
    """A routing decision. Same shape from the LLM router and the tuned one."""

    intents: frozenset[Intent] = field(default_factory=frozenset)
    confidence: float = 0.0
    #: Free-text rationale. The LLM router fills this; the tuned one won't.
    reasoning: str | None = None

    @property
    def agents(self) -> list[str]:
        """Distinct agents to dispatch to, stable order, self-handled intents dropped."""
        seen: list[str] = []
        for intent in sorted(self.intents, key=str):
            agent = AGENT_FOR.get(intent)
            if agent and agent not in seen:
                seen.append(agent)
        return seen

    @property
    def is_confident(self) -> bool:
        """Confidence in the decision itself — including a decision to abstain."""
        return self.confidence >= CONFIDENCE_FLOOR

    @property
    def should_dispatch(self) -> bool:
        return self.is_confident and bool(self.agents)

    @property
    def self_handled(self) -> bool:
        """True when no subagent is needed — smalltalk or a meta command."""
        return bool(self.intents) and not self.agents

    @property
    def is_rejection(self) -> bool:
        """Confidently out of scope — distinct from failing to understand.

        These want different replies, and the difference matters most in voice:
        "that's not something I do" versus "sorry, say that again?".
        """
        return not self.intents and self.is_confident

    def __str__(self) -> str:
        labels = ",".join(sorted(str(i) for i in self.intents)) or "none"
        return f"{labels} ({self.confidence:.2f})"


@runtime_checkable
class Router(Protocol):
    """Swap point for Phase 4. Keep this signature stable."""

    name: str

    def route(self, utterance: str) -> Route:
        """Classify one utterance. Must not raise — return a low-confidence
        empty Route on failure so the orchestrator can fall back gracefully."""
        ...


def parse_intents(raw: str) -> frozenset[Intent]:
    """Lenient parse of a comma/space separated label list.

    Shared by both routers: the LLM returns labels as text, and the fine-tuned
    model will be trained to emit the same format. Unknown labels are dropped
    rather than raising — a malformed generation should degrade, not crash.
    """
    valid = {i.value: i for i in Intent}
    tokens = (t.strip().strip(".\"'").lower() for t in raw.replace("\n", ",").split(","))
    return frozenset(valid[t] for t in tokens if t in valid)
