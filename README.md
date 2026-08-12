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
| 2 | Subagents: calendar, weather, news/sports | Done |
| 3 | Morning briefing (pre-computed, pushed) | Done |
| 4 | Fine-tuned router (LoRA on `llama3.2:3b`) | Done |
| 5 | Live sports dashboard | Done |
| 6 | Voice (Whisper → orchestrator → TTS) | Next |

---

## Agents

Each agent reads the cache (free, instant — the poller already did the work) and
uses the model to answer an arbitrary question over it. `handle()` answers
conversationally; `summary()` returns a templated digest in under 2ms with no
model call, which is what the morning briefing will use.

| Agent | Reads | Covers |
|---|---|---|
| `calendar` | `calendar` | your schedule, availability, what's next |
| `weather` | `weather` | forecast, advisories, precautions |
| `news` | `news`, `nba`, `nfl`, `f1`, `cricket` | headlines and sport |

## Morning briefing

```bash
python brief.py                  # print it
python brief.py --speak          # read it aloud
python brief.py --notify         # macOS notification
```

Composed entirely from templated `brief()` calls — **~5ms, no model call**. That
is deliberate: it fires unattended at dawn, so it has to be deterministic and it
has to work when Ollama is down. A briefing that intermittently fails is one you
stop trusting, then stop reading.

Three renderings, because the constraints genuinely differ. The terminal takes
structure; speech can't (headings and bracketed state codes read terribly
aloud); a notification gets two lines before macOS truncates, so it carries only
enough to make you go and read the rest.

It reports its own staleness. A briefing confidently quoting yesterday's
forecast is worse than one admitting it couldn't reach the data.

### Running it daily

```bash
./scripts/install_launchd.sh --dry-run   # preview, installs nothing
./scripts/install_launchd.sh             # poller + 07:00 briefing
./scripts/install_launchd.sh --speak --hour 6
./scripts/install_launchd.sh --uninstall
```

Installs two launchd agents: the poller (`KeepAlive`, so it restarts if it dies
and survives reboot) and the briefing on a calendar interval. launchd over cron
because it handles both of those and needs no login shell.

## Dashboard

```bash
python dashboard/server.py        # http://localhost:8765
```

Live scores, fixtures and per-source health for NBA, NFL, F1 and cricket, plus a
weather and next-meeting strip. Refreshes every 15s.

**It reads the cache and fetches nothing.** The poller remains the only thing
that touches an upstream, so opening the page in ten tabs costs nothing and
cannot blow a rate limit. stdlib `http.server` — a localhost read-only view over
a SQLite file doesn't earn a web framework.

Every state is a **colour plus a word**: `LIVE`, `FINAL`, `UPCOMING`, and per
source `live data` / `stale` / `failing` / `no data`. A bare coloured dot is
unreadable for colour-blind users and vanishes in forced-colors mode, so the
status colour never carries the meaning by itself. Light and dark are both
defined from the same tokens rather than one being an automatic flip of the
other.

## Data sources

All free, no API keys required.

| Source | Provider | Interval |
|---|---|---|
| Calendar | macOS Calendar.app via AppleScript | 10 min |
| Weather | Open-Meteo | 15 min |
| Advisories | US National Weather Service | 5 min while an alert is active |
| Headlines | RSS (BBC, NPR, Ars Technica, HN) | 30 min |
| NBA | ESPN scoreboard + `nba_api` standings | 60s live / 15 min / 6h idle |
| NFL, F1, Cricket | ESPN scoreboard | same dynamic pacing |

Calendar reads Calendar.app rather than the Google Calendar API — the Google
account is already synced there, so there's no OAuth flow, no credentials file
and no token refresh. The query takes ~18s, which is precisely why it sits
behind the poller.

`nba.com`'s live CDN returns 403 to non-browser clients, so ESPN is the games
source throughout. Its `status.type.state` (`pre`/`in`/`post`) is uniform across
every sport, which is what lets one client cover all four.

## Known limitations

**Agent latency.** 7–12s per agent on `llama3.1:8b`. Parallel dispatch means a
three-agent request costs roughly one agent, but a single turn is still slow.

**Instruction-following.** The 8B model doesn't reliably respect "stay in your
own domain" or "don't embellish the data", so a request routed to two agents can
produce one section answering outside its remit. Structural fixes beat
instructions here — removing a heading from the context stopped it being echoed
after three rounds of telling it not to. Setting `JARVIS_PROVIDER=anthropic`
swaps the model without touching anything else.

**Out-of-season leagues.** ESPN keeps serving a league's last completed fixture,
so cricket currently returns a May IPL final. Every event carries its date for
that reason. Enumerating in-season league IDs is outstanding.

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

### Results — fine-tuned 3B vs the 8B baseline

Measured on 94 held-out examples the fine-tune never saw. `prepare_data.py`
fails the build on any train/test collision, because training on your eval set
is both fatal and silent.

| | Baseline `llama3.1:8b` | Fine-tuned `llama3.2:3b` | |
|---|---|---|---|
| Exact set match | 86.2% | 91.5% | +5.3pp, **not significant** |
| Macro-F1 | 0.885 | 0.947 | +7.0% |
| Latency | 857ms | **372ms** | **2.3× faster** |

**The latency result is solid; the accuracy result is not established.** McNemar's
exact test on the paired runs gives **p = 0.302** — the tuned router fixed 10
examples and broke 5, which at 15 discordant pairs is well within chance. The
95% intervals overlap heavily: baseline [77.8, 91.7], tuned [84.1, 95.6].

The improvement may be real. A 94-example test set simply cannot demonstrate it.
Detecting a 5pp difference at this discordance rate needs roughly **300 test
examples**; growing the test set is worth more than any further training, because
without it a better model is unmeasurable.

Latency needs no such caveat — 2.3× is a systematic measurement across 94 runs,
not a noisy proportion. It comes off a 14MB LoRA adapter trained in ~7 minutes
on an M4.

```bash
python evals/significance.py   # McNemar + Wilson intervals on any two saved runs
```

| Slice | Baseline | Tuned |
|---|---|---|
| negative (should abstain) | 83.3% | **100%** |
| voice (spoken phrasing) | 62.5% | **100%** |
| core | 94.9% | 96.6% |
| multi (compound requests) | 78.6% | 78.6% |
| ambiguous | 57.1% | 57.1% |

Exact set match is the headline: a route counts only if it predicts *precisely*
the right label set. Partial credit would flatter the multi-intent slice, which
is the one that decides whether a 3B is usable at all.

**Read the small slices with care.** `voice` is n=8 and `ambiguous` n=7, so a
single example moves them ~14pp. Only the overall figure and `core` (n=59) carry
enough weight to be trusted on their own.

**Multi-label needed deliberate over-weighting.** The first fine-tune scored
64.3% on `multi` — worse than the baseline — because only 40 of 256 training
examples were compound and the model defaulted to emitting one label. Raising
that to 97 of 319 recovered it to 78.6% with no loss elsewhere. Matching the
real-world distribution was the wrong instinct; hard cases need over-representing.

**Calibration improved less than hoped.** Confidence is the geometric mean of
generated-token probabilities — a real property of the model's distribution
rather than a self-reported number. Confident predictions are right 92.4% of the
time against 50% for unsure ones, so the signal is directional, but only 2 of 94
predictions fall below the floor. Abstention still rarely fires. The encouraging
case is "tell me a joke" at 0.20 — correctly uncertain on a genuinely ambiguous
label — but n=2 is too small to claim the win.

```bash
./training/train.sh                                       # reproduce end to end
python evals/run_routing.py --router tuned                # evaluate
python evals/run_routing.py --router tuned --compare evals/results/llm-llama31-8b-v2.json
JARVIS_ROUTER=tuned python main.py "brief me"             # use it
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
