"""LLM-backed router — the Phase 1 baseline.

Its job is twofold: route well enough to build the rest of the system on, and
establish the accuracy/latency numbers the fine-tuned router gets measured
against in Phase 4. Keep it honest — an over-engineered baseline makes the
fine-tune look worse than it is.

Output format is a bare label list plus a confidence, deliberately identical to
what the tuned model will be trained to emit, so `parse_intents` is shared and
the swap changes nothing downstream.
"""
import logging
import re

from core.llm import LLM, get_llm
from core.router.base import Intent, Route, parse_intents

log = logging.getLogger("jarvis.router")

# The few-shot block lives in the system prompt, and the user message carries the
# utterance alone. Putting both in one user message made the model continue the
# pattern — it invented a fresh example and labelled that instead of the input.
SYSTEM_PROMPT = """You classify what a personal assistant is being asked to do.

Labels:
  calendar   meetings, scheduling, availability, reminders about events
  weather    forecast, temperature, rain, heat/storm advisories, what to wear
  sports     scores, standings, fixtures, results (NBA, NFL, F1, cricket)
  news       headlines, current events, world/business/tech news
  smalltalk  greetings, thanks, banter, questions about how you are
  system     what you can do, repeat that, stop, cancel, change a setting

This assistant does ONLY those six things. It does not write code, answer
trivia, do translation, or place orders. When a request falls outside the list,
answer `labels: none` — that is a correct answer, not a failure.

Boundaries that are easy to get wrong:
- A wake word, greeting or filler wrapped around a real request is framing, not
  a second intent. "hey jarvis what's the weather" is weather alone. Label
  smalltalk only when the whole utterance is social and asks for nothing.
- calendar means the user's own schedule. When a public fixture is on is sports,
  not calendar, even though it asks "when".
- system is about the assistant itself — its capabilities, settings, repeating
  or stopping itself. Cancelling a meeting is calendar.

Reply with exactly two lines and nothing else:
labels: <comma-separated labels, or none>
confidence: <0.0-1.0>

Apply more than one label only when the request genuinely needs two different
things done. Prefer the single label that captures what is being asked. Use a
low confidence when the request is ambiguous.

Worked examples:

INPUT: what's on my calendar tomorrow
labels: calendar
confidence: 0.97

INPUT: do I need an umbrella this afternoon
labels: weather
confidence: 0.95

INPUT: did the lakers win last night
labels: sports
confidence: 0.96

INPUT: give me the rundown for today
labels: calendar,weather,news
confidence: 0.88

INPUT: should I bring a jacket to my 3pm
labels: calendar,weather
confidence: 0.85

INPUT: hey jarvis
labels: smalltalk
confidence: 0.94

INPUT: what can you actually do
labels: system
confidence: 0.92

INPUT: sdfkjh
labels: none
confidence: 0.05

INPUT: write me a python script to parse csv
labels: none
confidence: 0.90

INPUT: what's the capital of peru
labels: none
confidence: 0.90"""

CONFIDENCE_RE = re.compile(r"confidence:\s*([0-9]*\.?[0-9]+)", re.I)
LABELS_RE = re.compile(r"labels:\s*(.*)", re.I)


class LLMRouter:
    name = "llm"

    def __init__(self, llm: LLM | None = None):
        self.llm = llm or get_llm()
        self.name = f"llm:{self.llm.model}"

    def route(self, utterance: str) -> Route:
        if not utterance.strip():
            return Route()
        try:
            raw = self.llm.complete(
                system=SYSTEM_PROMPT,
                user=f"INPUT: {utterance.strip()}",
                max_tokens=48,
            )
        except Exception as e:
            # Never raise: the orchestrator needs a decision it can fall back on.
            log.warning("router failed on %r: %s", utterance[:60], e)
            return Route(reasoning=f"router error: {e}")
        return self._parse(raw)

    @staticmethod
    def _parse(raw: str) -> Route:
        labels_match = LABELS_RE.search(raw)
        intents = parse_intents(labels_match.group(1) if labels_match else raw)

        confidence_match = CONFIDENCE_RE.search(raw)
        try:
            confidence = float(confidence_match.group(1)) if confidence_match else 0.0
        except ValueError:
            confidence = 0.0

        # Empty intents means one of two very different things. An explicit
        # "none" is a real decision that the request is out of scope, and its
        # stated confidence stands. Labels that were present but unparseable are
        # a malformed generation, so the stated confidence is not trustworthy.
        if not intents:
            said_none = bool(labels_match) and "none" in labels_match.group(1).lower()
            if not said_none:
                confidence = min(confidence, 0.2)

        return Route(
            intents=intents,
            confidence=max(0.0, min(1.0, confidence)),
            reasoning=raw.strip()[:200],
        )
