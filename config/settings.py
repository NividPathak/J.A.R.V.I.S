"""Central configuration. Everything env-driven, with sane local defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# Identity
JARVIS_NAME = os.getenv("JARVIS_NAME", "J.A.R.V.I.S")
JARVIS_USER = os.getenv("JARVIS_USER", "Nivid")

# Runtime state — gitignored
VAR_DIR = ROOT / "var"
VAR_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DB = Path(os.getenv("JARVIS_CACHE_DB", VAR_DIR / "cache.db"))

# Model backends
LLM_PROVIDER = os.getenv("JARVIS_PROVIDER", "ollama")  # ollama | anthropic
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")

# Router — swapped from LLM to fine-tuned adapter in Phase 4
ROUTER_BACKEND = os.getenv("JARVIS_ROUTER", "llm")  # llm | tuned
ROUTER_MODEL = os.getenv("JARVIS_ROUTER_MODEL", "llama3.2:3b")

# Data source credentials
CRICKET_API_KEY = os.getenv("CRICKET_API_KEY", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

# Where the user is, for weather and advisories
HOME_LAT = float(os.getenv("JARVIS_LAT", "0") or 0)
HOME_LON = float(os.getenv("JARVIS_LON", "0") or 0)
TIMEZONE = os.getenv("JARVIS_TZ", "America/New_York")
