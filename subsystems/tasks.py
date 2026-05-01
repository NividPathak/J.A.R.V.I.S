"""Hierarchical task management — decompose, track, and execute."""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from config.settings import MEMORY_DIR

_TASK_FILE = MEMORY_DIR / "tasks.json"


def _load() -> List[Dict]:
    if _TASK_FILE.exists():
        return json.loads(_TASK_FILE.read_text())
    return []


def _save(tasks: List[Dict]) -> None:
    _TASK_FILE.write_text(json.dumps(tasks, indent=2))


def add_task(title: str, subtasks: List[str] = None, priority: str = "normal") -> str:
    """Add a task with optional subtasks."""
    tasks = _load()
    task = {
        "id": len(tasks) + 1,
        "title": title,
        "priority": priority,
        "status": "pending",
        "subtasks": [{"text": s, "done": False} for s in (subtasks or [])],
        "created": datetime.now().isoformat(),
    }
    tasks.append(task)
    _save(tasks)
    sub_info = f" ({len(subtasks)} subtasks)" if subtasks else ""
    return f"Task #{task['id']} added: '{title}'{sub_info}"


def complete_task(task_id: int) -> str:
    """Mark a task as complete."""
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id:
            t["status"] = "completed"
            t["completed"] = datetime.now().isoformat()
            _save(tasks)
            return f"Task #{task_id} '{t['title']}' marked complete."
    return f"Task #{task_id} not found."


def list_tasks(status: str = "pending") -> str:
    """List tasks by status."""
    tasks = _load()
    filtered = [t for t in tasks if t["status"] == status]
    if not filtered:
        return f"No {status} tasks."
    lines = []
    for t in filtered:
        subtask_info = ""
        if t["subtasks"]:
            done = sum(1 for s in t["subtasks"] if s["done"])
            subtask_info = f" [{done}/{len(t['subtasks'])} subtasks]"
        lines.append(f"  #{t['id']} [{t['priority'].upper()}] {t['title']}{subtask_info}")
    return "\n".join(lines)


def decompose(goal: str) -> List[str]:
    """Simple rule-based decomposition placeholder — LLM handles this."""
    return [f"Analyze: {goal}", f"Plan: {goal}", f"Execute: {goal}", f"Verify: {goal}"]
