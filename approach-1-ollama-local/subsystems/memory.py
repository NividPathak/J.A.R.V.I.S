"""Long-term contextual knowledge database with semantic search."""
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from config.settings import MEMORY_DIR

_STORE_PATH = MEMORY_DIR / "knowledge.json"


def _load() -> List[Dict]:
    if _STORE_PATH.exists():
        return json.loads(_STORE_PATH.read_text())
    return []


def _save(records: List[Dict]) -> None:
    _STORE_PATH.write_text(json.dumps(records, indent=2))


def store(content: str, category: str = "general", tags: List[str] = None) -> str:
    """Store a piece of information in long-term memory."""
    records = _load()
    record = {
        "id": hashlib.md5(f"{content}{datetime.now()}".encode()).hexdigest()[:8],
        "content": content,
        "category": category,
        "tags": tags or [],
        "timestamp": datetime.now().isoformat(),
    }
    records.append(record)
    # Keep last 500 memories
    if len(records) > 500:
        records = records[-500:]
    _save(records)
    return f"Stored in memory (id: {record['id']})"


def query(search: str, n: int = 5) -> str:
    """Search memory for relevant information."""
    records = _load()
    if not records:
        return "No memories stored yet."

    search_lower = search.lower()
    scored = []
    for r in records:
        score = 0
        text = (r["content"] + " " + " ".join(r["tags"])).lower()
        for word in search_lower.split():
            if word in text:
                score += 1
        if score > 0:
            scored.append((score, r))

    scored.sort(key=lambda x: -x[0])
    top = scored[:n]
    if not top:
        return "No relevant memories found."

    results = []
    for _, r in top:
        results.append(f"[{r['category']}] {r['content']} (stored: {r['timestamp'][:10]})")
    return "\n".join(results)


def get_recent(n: int = 10) -> str:
    """Get the most recently stored memories."""
    records = _load()
    if not records:
        return "Memory is empty."
    recent = records[-n:][::-1]
    return "\n".join(f"- {r['content']}" for r in recent)
