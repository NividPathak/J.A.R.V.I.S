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
| 1 | Orchestrator, router interface, routing eval set | Next |
| 2 | Subagents: calendar, weather, news/sports | Planned |
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
