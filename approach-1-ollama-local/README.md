# Approach 1 — Ollama Local (Free)

**Engine:** `llama3.1:8b` running locally via Ollama
**Cost:** $0 — runs entirely on your machine
**Hardware:** Tested on Apple M4 16GB RAM

## Setup

```bash
brew install ollama && brew services start ollama
ollama pull llama3.1:8b
pip install -r requirements.txt
cp .env.example .env   # add TAVILY_API_KEY for better search
python main.py
```

## Commands
| Command | Action |
|---------|--------|
| `/status` | System CPU, RAM, battery |
| `/memory` | Show recent memories |
| `/tasks` | Show pending tasks |
| `/clear` | Clear conversation history |
| `/switch` | Info on changing models |
| `/exit` | Quit |

## Tools Available
- `nba_today` — Live NBA games and scores
- `nba_standings` — Playoff picture
- `web_search` — Tavily or DuckDuckGo
- `news` — Latest news on any topic
- `web_fetch` — Fetch any URL
- `system_status` — CPU/RAM/battery
- `notify` — Desktop notification
- `speak` — Text-to-speech
- `open_app` / `open_url` — Launch apps/URLs
- `write_file` / `read_file` — File I/O
- `set_volume` — System volume
- `memory_store` / `memory_query` — Long-term memory
- `add_task` / `list_tasks` / `complete_task` — Task manager
