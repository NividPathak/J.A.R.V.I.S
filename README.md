# J.A.R.V.I.S

### Just A Rather Very Intelligent System

A personal AI assistant built as an **agent orchestrator**: a router dispatches
each request to a specialist subagent, and a shared cache-backed data layer
feeds both conversation and a live dashboard.

---

## Architecture

```
              voice / text in
                     │
                     ▼
              ┌─────────────┐
              │   Router    │   intent → subagent
              │  (Phase 4:  │   swappable: LLM now,
              │  fine-tuned)│   fine-tuned 3B later
              └──────┬──────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
 ┌────────┐    ┌──────────┐    ┌──────────┐
 │calendar│    │ weather  │    │  news +  │
 │ agent  │    │ + alerts │    │  sports  │
 └────────┘    └─────┬────┘    └─────┬────┘
                     │               │
                     └───────┬───────┘
                             ▼
                    ┌─────────────────┐
                    │   data layer    │  ← the only thing that
                    │  poller → cache │    talks to upstreams
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
              morning briefing    dashboard
```

**The data layer is the foundation.** One poller is the single writer; agents and
the dashboard are readers. Nothing fetches on demand. That means each source's
poll interval *is* its rate limit — there's no second code path that can quietly
blow a free-tier budget — and a dead upstream degrades one tile rather than
blanking the page.

---

## Status

| Phase | What | State |
|---|---|---|
| 0 | Data layer — cache, poller, source contract | Done |
| 1 | Orchestrator, router interface, routing eval set | Done |
| 2 | Subagents: calendar, weather, news/sports | Next |
| 3 | Morning briefing (pre-computed, pushed) | Planned |
| 4 | Fine-tuned router (LoRA on `llama3.2:3b`) | Planned |
| 5 | Live sports dashboard | Planned |
| 6 | Voice (Whisper → orchestrator → TTS) | Planned |

---

## Data sources

All free, no API keys required.

| Sport | Source | Verified |
|---|---|---|
| NBA | ESPN scoreboard + `nba_api` standings | Working |
| NFL | ESPN scoreboard | Working |
| F1 | ESPN scoreboard | Working |
| Cricket | ESPN scoreboard (league-scoped, e.g. `cricket/8048`) | Working |

`nba.com`'s live CDN returns 403 to non-browser clients, so ESPN is the games
source throughout. Its `status.type.state` (`pre`/`in`/`post`) is uniform across
every sport, which is what lets one client cover all four.

---

## Routing

The router predicts a *set* of intents; a mapping turns intents into agents.
Intents are finer-grained than agents on purpose — `sports` and `news` share one
agent today, and splitting them later is a one-line change that leaves the
labelled dataset valid.

Routing is multi-label because "what does my day look like" genuinely needs
calendar, weather and news at once — that request *is* the morning briefing.

`Router` is a two-method protocol so the Phase 4 fine-tuned model drops in
without a caller changing.

### Baseline — `llama3.1:8b`, 94 examples

| Metric | |
|---|---|
| Exact set match | **86.2%** |
| Macro-F1 | 0.885 |
| Latency | 857ms mean / 987ms p95 |

| Slice | Exact match |
|---|---|
| core | 94.9% |
| negative (should abstain) | 83.3% |
| multi (compound requests) | 78.6% |
| voice (spoken phrasing) | 62.5% |
| ambiguous | 57.1% |

Exact set match is the headline: a route counts only if it predicts *precisely*
the right label set. Partial credit would flatter the multi-intent slice, which
is the one that decides whether a 3B model is usable here.

**Known weakness — calibration.** 93 of 94 predictions land above the confidence
floor, so abstention almost never fires and ~13 routes are confidently wrong.
An LLM asked to self-report confidence mostly says 0.85–0.95 regardless of
whether it's right. Real softmax probabilities from a fine-tuned classifier are
the fix, and making abstention actionable is a large part of Phase 4's value.

```bash
python evals/run_routing.py                              # full set
python evals/run_routing.py --tag voice                  # one slice
python evals/run_routing.py --compare evals/results/llm-llama31-8b-v2.json
```

## Quick start

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env          # optional — defaults work for the data layer

./.venv/bin/python poll.py status    # what's cached, how old, what's broken
./.venv/bin/python poll.py once -f   # force a refresh
./.venv/bin/python poll.py run       # the daemon
```

---

## Layout

```
config/settings.py      env-driven configuration
data/cache.py           SQLite store; stale-while-error semantics
data/poller.py          the single writer
data/sources/base.py    Source contract + free-tier budget guard
data/sources/nba.py     reference implementation
integrations/espn.py    one client, every sport
integrations/nba_client.py  standings via nba_api
integrations/macos.py   notifications, TTS, files, volume
evals/routing/          Phase 1 routing eval set
```

## Adding a source

Subclass `Source`, declare `name`, `ttl` and (if the upstream is rate-limited)
`daily_budget`, implement `fetch()` returning structured data, and register it in
`poll.py`. Override `interval()` to poll hard only while something is happening —
see `data/sources/nba.py`. `validate_budget()` catches pacing that would exceed a
free tier at startup, before it burns the quota.
