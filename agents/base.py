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


PERSONA = """You are J.A.R.V.I.S, a personal assistant. Concise and precise, dry
wit, no filler. Address the user as "sir" occasionally and naturally, not every
line.

Answer only from the DATA provided. It is the live state of the system — if the
answer isn't in it, say so plainly rather than guessing. Never invent a score, a
temperature, a headline or a meeting.

Stay inside your own domain. Several specialists may answer the same request in
parallel, each from different data. Answer only the part yours covers and ignore
the rest — do not comment on what your data doesn't contain, and never speculate
about another domain from loosely related material.

Lead with anything marked urgent or advisory.

Report what the data says and nothing beyond it. Don't round, embellish or infer
extra detail — a score of 155/8 is 155 for 8, not "bowled out". Every item is
dated; if something is not from today, say when it was rather than implying it
is current.

Write plain prose to a person. Never echo the data's own headings, labels,
brackets or field names — those are scaffolding for you, not words to repeat.
Two or three sentences unless more is genuinely needed."""


class CachedAgent:
    """Base for agents that answer from the cache.

    The read is free and instant because the poller already did the work. The
    LLM call is what turns a fixed digest into something that can answer an
    arbitrary question — "do I have anything before my flight" isn't a template.
    """

    name: str
    description: str
    #: cache keys this agent reads
    sources: tuple[str, ...] = ()

    def __init__(self, cache=None, llm=None):
        from core.llm import get_llm
        from data.cache import Cache

        self._cache = cache or Cache()
        self._llm = llm or get_llm()

    def entries(self) -> dict:
        return {name: self._cache.get(name) for name in self.sources}

    def context(self) -> str:
        """Serialise what this agent knows, for the model. Override per agent."""
        raise NotImplementedError

    def summary(self) -> str:
        """One line. Templated, no model call. Override per agent."""
        raise NotImplementedError

    def brief(self) -> str:
        """This agent's section of the morning briefing.

        Templated like `summary()` and for the same reason: the briefing fires
        unattended at dawn, so it has to be deterministic and it has to work
        when the model is down. Richer than `summary()` because it's the whole
        of what gets read out, not a fragment of a sentence.
        """
        return self.summary()

    def handle(self, utterance: str) -> str:
        context = self.context()
        if not context.strip():
            return f"I don't have current {self.name} data, sir."
        return self._llm.complete(
            system=PERSONA,
            user=f"DATA:\n{context}\n\nREQUEST: {utterance}",
            max_tokens=300,
        )

    def _staleness_note(self) -> str:
        """Warn the model when data is old, so it can hedge rather than assert."""
        notes = []
        for name, entry in self.entries().items():
            if entry is None or entry.payload is None:
                notes.append(f"({name} unavailable)")
            elif entry.is_stale:
                mins = int((entry.age or 0) / 60)
                notes.append(f"({name} last updated {mins} min ago)")
        return " ".join(notes)


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
