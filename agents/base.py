"""The subagent contract.

A subagent owns one domain end to end: it reads what it needs (almost always
from the cache, never from an upstream directly) and returns prose the
orchestrator can hand back or compose.

Kept this narrow so Phase 2 can fill in real agents without the orchestrator
changing, and so a stub is a drop-in for a real one.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class AgentReply:
    agent: str
    text: str
    ok: bool = True
    #: Seconds spent. Recorded because the parallel-dispatch win is only real if
    #: it's measured — a briefing is as slow as its slowest agent.
    elapsed: float = 0.0


@runtime_checkable
class Agent(Protocol):
    name: str
    #: One line, used when the assistant is asked what it can do.
    description: str

    def handle(self, utterance: str) -> str:
        """Answer within this agent's domain. May raise; the orchestrator catches."""
        ...


class StubAgent:
    """Placeholder so the full loop runs before Phase 2 lands.

    Deliberately says it isn't built rather than inventing an answer — a stub
    that fabricates plausible output is worse than no stub, because it hides
    which parts of the system actually work.
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    def handle(self, utterance: str) -> str:
        return f"[{self.name}] not built yet — Phase 2. Asked: {utterance!r}"
