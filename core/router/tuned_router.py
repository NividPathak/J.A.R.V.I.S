"""Fine-tuned router — LoRA on Llama-3.2-3B, served through MLX.

Drops in behind the same `Router` protocol as the LLM baseline, so swapping it
in changes nothing above it.

The interesting part isn't speed, it's calibration. Asking an LLM to report its
own confidence produced 0.85-0.95 almost regardless of correctness, so
abstention never fired and ~13 of 94 baseline routes were confidently wrong.
Here confidence is the geometric mean of the generated tokens' probabilities —
an actual property of the model's distribution rather than a number it made up.
"""
import logging
import math
from pathlib import Path

from core.router.base import TUNED_SYSTEM, Route, parse_intents

log = logging.getLogger("jarvis.router")

ROOT = Path(__file__).parent.parent.parent
DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"
DEFAULT_ADAPTER = ROOT / "training" / "adapters"
#: Targets are a short label list; anything longer means the model is rambling.
MAX_TOKENS = 16


class TunedRouter:
    name = "tuned"

    def __init__(self, model: str = DEFAULT_MODEL, adapter_path: Path | str | None = DEFAULT_ADAPTER):
        from mlx_lm import load

        adapter = str(adapter_path) if adapter_path and Path(adapter_path).exists() else None
        if adapter is None:
            log.warning("no adapter at %s — running the base model untuned", adapter_path)
        self._model, self._tokenizer = load(model, adapter_path=adapter)
        self.name = f"tuned:{Path(model).name}" + ("" if adapter else ":no-adapter")

    def route(self, utterance: str) -> Route:
        if not utterance.strip():
            return Route()
        try:
            text, confidence = self._generate(utterance.strip())
        except Exception as e:
            # Same contract as the LLM router: never raise, let the orchestrator
            # fall back on a low-confidence empty route.
            log.warning("tuned router failed on %r: %s", utterance[:60], e)
            return Route(reasoning=f"router error: {e}")

        intents = parse_intents(text)
        said_none = "none" in text.lower()
        if not intents and not said_none:
            # Unparseable output — the stated probability is not evidence the
            # answer is usable.
            confidence = min(confidence, 0.2)
        return Route(intents=intents, confidence=confidence, reasoning=text.strip()[:120])

    def _generate(self, utterance: str) -> tuple[str, float]:
        from mlx_lm.generate import stream_generate

        prompt = self._tokenizer.apply_chat_template(
            [
                {"role": "system", "content": TUNED_SYSTEM},
                {"role": "user", "content": utterance},
            ],
            add_generation_prompt=True,
        )

        pieces: list[str] = []
        logprobs: list[float] = []
        for response in stream_generate(
            self._model, self._tokenizer, prompt, max_tokens=MAX_TOKENS
        ):
            pieces.append(response.text)
            # `logprobs` is the distribution over the vocabulary; index it at the
            # token actually emitted to get that choice's log-probability.
            logprobs.append(float(response.logprobs[response.token]))

        text = "".join(pieces)
        # Geometric mean of per-token probabilities. Length-normalised, so a
        # two-label answer isn't penalised for being longer than a one-label one.
        confidence = math.exp(sum(logprobs) / len(logprobs)) if logprobs else 0.0
        return text, max(0.0, min(1.0, confidence))
