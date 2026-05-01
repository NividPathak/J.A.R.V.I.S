# J.A.R.V.I.S
### Just A Rather Very Intelligent System

A personal AI assistant built progressively — starting free and local, scaling up to full cloud intelligence as needed.

---

## Architecture

Each approach lives in its own folder so results can be directly compared.

| Folder | Engine | Cost | Status |
|--------|--------|------|--------|
| [`approach-1-ollama-local`](./approach-1-ollama-local) | Ollama `llama3.1:8b` (local) | Free | ✅ Built |
| [`approach-2-hybrid`](./approach-2-hybrid) | Local + Claude API fallback | Near-free | 🔜 Next |
| [`approach-3-claude-haiku`](./approach-3-claude-haiku) | Claude Haiku 4.5 | ~$0.001/turn | 🔜 Planned |
| [`approach-4-claude-opus`](./approach-4-claude-opus) | Claude Opus 4.7 | ~$0.10/turn | 🔜 Planned |

---

## Features (all approaches)
- **Contextual reasoning** — "Get rid of him" → social deflection, not harm
- **Proactive tool use** — never asks for URLs; searches itself
- **NBA live data** — real-time scores and matchups via `nba_api`
- **Web search** — Tavily (AI-summarised) with DuckDuckGo fallback
- **Long-term memory** — persistent knowledge store across sessions
- **macOS integration** — notifications, app control, file I/O, volume, TTS
- **Task management** — hierarchical task decomposition and tracking

---

## Quick Start (Approach 1 — Free Local)

```bash
# 1. Install Ollama
brew install ollama && brew services start ollama

# 2. Pull the model
ollama pull llama3.1:8b

# 3. Install dependencies
cd approach-1-ollama-local
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Optional: add TAVILY_API_KEY for better web search

# 5. Run
python main.py
```

---

## Built With
- [Ollama](https://ollama.com) — local LLM runtime
- [nba_api](https://github.com/swar/nba_api) — real-time NBA data
- [Tavily](https://tavily.com) — AI-optimised web search
- [Rich](https://github.com/Textualize/rich) — terminal UI
- [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) — Claude API (future approaches)
