"""macOS integration via AppleScript and subprocess.

Ported from the previous build. One fix on the way in: notification text is now
escaped before it reaches AppleScript. The old version interpolated raw strings,
so any headline containing a quote or backslash broke the call — which the
morning briefing would have hit on roughly its first run.
"""
import subprocess
from pathlib import Path

READ_FILE_LIMIT = 3000


def _as_applescript_string(s: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def notify(title: str, message: str, subtitle: str = "") -> str:
    """Send a macOS desktop notification."""
    script = (
        f"display notification {_as_applescript_string(message)} "
        f"with title {_as_applescript_string(title)}"
    )
    if subtitle:
        script += f" subtitle {_as_applescript_string(subtitle)}"
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return f"Notification sent: {title}"
    except Exception as e:
        return f"Notification failed: {e}"


def speak(text: str, voice: str = "Samantha") -> str:
    """Text-to-speech via the macOS `say` command. Non-blocking."""
    try:
        subprocess.Popen(["say", "-v", voice, text])
        return f"Speaking: {text[:50]}..."
    except Exception as e:
        return f"Speech failed: {e}"


def open_app(app_name: str) -> str:
    try:
        result = subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
        if result.returncode == 0:
            return f"Opened {app_name}."
        return f"Could not open {app_name}: {result.stderr.strip()}"
    except Exception as e:
        return f"Failed to open app: {e}"


def open_url(url: str) -> str:
    try:
        subprocess.Popen(["open", url])
        return f"Opened {url} in browser."
    except Exception as e:
        return f"Failed to open URL: {e}"


def run_shortcut(name: str) -> str:
    """Run a macOS Shortcut by name."""
    try:
        result = subprocess.run(
            ["shortcuts", "run", name], capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return f"Shortcut '{name}' executed."
        return f"Shortcut failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Failed to run shortcut: {e}"


def write_file(path: str, content: str) -> str:
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"File written: {p}"
    except Exception as e:
        return f"Failed to write file: {e}"


def read_file(path: str) -> str:
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"File not found: {path}"
        text = p.read_text()
        if len(text) > READ_FILE_LIMIT:
            return text[:READ_FILE_LIMIT] + f"\n... [truncated at {READ_FILE_LIMIT} chars]"
        return text
    except Exception as e:
        return f"Failed to read file: {e}"


def set_volume(level: int) -> str:
    """Set system volume (0-100)."""
    level = max(0, min(100, int(level)))
    try:
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {level}"],
            check=True, capture_output=True,
        )
        return f"Volume set to {level}%."
    except Exception as e:
        return f"Failed to set volume: {e}"
