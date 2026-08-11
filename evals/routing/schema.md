# Routing eval set

JSONL, one example per line:

```json
{"utterance": "do I need an umbrella this afternoon", "intents": ["weather"], "tag": "core"}
```

| Field | Meaning |
|---|---|
| `utterance` | Exactly what gets said or typed. Keep the phrasing natural, including voice-style filler. |
| `intents` | Sorted list of labels. Empty `[]` means nothing matched — the router should abstain. |
| `tag` | Slice for reporting: `core`, `multi`, `voice`, `ambiguous`, `negative`. |

## This set has two jobs

1. **Regression test** for the LLM router, from now on.
2. **Training data** for the Phase 4 fine-tune of `llama3.2:3b`.

That second job is why examples are labelled by *intent* and not by agent — see
`core/router/base.py`. Splitting an agent later must not invalidate the corpus.

## Labelling rules

- **Label what's asked, not what answering it requires.** "Did the Lakers win"
  is `sports`, even though answering also touches the cache and the clock.
- **Multi-label only when genuinely compound.** "Should I bring a jacket to my
  3pm" needs both the calendar and the forecast, so it's `calendar,weather`.
  "What's the weather" is `weather` alone.
- **`smalltalk` and `system` map to no agent** — the orchestrator answers those
  itself. They're in the taxonomy so the router learns not to dispatch on them.
- **Empty `intents` is a real label**, not a gap. Abstention is a behaviour worth
  training and measuring; a confidently-wrong route is worse than a question.

## Slices

| Tag | What it covers | Why it's separate |
|---|---|---|
| `core` | One intent, plainly phrased | The floor — near-perfect accuracy expected |
| `multi` | Genuinely compound requests | Hardest slice; where a 3B model will struggle |
| `voice` | Spoken phrasing, wake words, disfluency | Phase 6 depends on this holding up |
| `ambiguous` | Reasonable people would disagree | Watch calibration, not just accuracy |
| `negative` | Nonsense, out of scope | Should abstain, not guess |

## Growing the set

Hand-written seed first — it defines what "correct" means. Expansion by LLM
paraphrase is fine for `core`, but keep `multi` and `ambiguous` hand-written:
those are where a generated example most often carries a wrong label, and a
wrong label in the eval set is worse than a missing one.

Target for a usable fine-tune is a few hundred to low thousands, with the
`core:multi` ratio kept roughly at what real usage looks like.
