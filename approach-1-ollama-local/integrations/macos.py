"""macOS system integration via AppleScript and subprocess."""
import subprocess
import os
from pathlib import Path


def notify(title: str, message: str, subtitle: str = "") -> str:
    """Send a macOS desktop notification."""
    script = f'display notification "{message}" with title "{title}"'
    if subtitle:
        script += f' subtitle "{subtitle}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return f"Notification sent: {title}"
    except Exception as e:
        return f"Notification failed: {e}"


def speak(text: str, voice: str = "Samantha") -> str:
    """Text-to-speech via macOS say command."""
    try:
        subprocess.Popen(["say", "-v", voice, text])
        return f"Speaking: {text[:50]}..."
    except Exception as e:
        return f"Speech failed: {e}"


def open_app(app_name: str) -> str:
    """Open a macOS application."""
    try:
        result = subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
        if result.returncode == 0:
            return f"Opened {app_name}."
        return f"Could not open {app_name}: {result.stderr.strip()}"
    except Exception as e:
        return f"Failed to open app: {e}"


def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    try:
        subprocess.Popen(["open", url])
        return f"Opened {url} in browser."
    except Exception as e:
        return f"Failed to open URL: {e}"


def run_shortcut(name: str) -> str:
    """Run a macOS Shortcut by name."""
    try:
        result = subprocess.run(
            ["shortcuts", "run", name],
            capture_output=True, text=True, timeout=30
        )
        return f"Shortcut '{name}' executed." if result.returncode == 0 else f"Shortcut failed: {result.stderr}"
    except Exception as e:
        return f"Failed to run shortcut: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"File written: {p}"
    except Exception as e:
        return f"Failed to write file: {e}"


def read_file(path: str) -> str:
    """Read content from a file."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"File not found: {path}"
        return p.read_text()[:3000]
    except Exception as e:
        return f"Failed to read file: {e}"


def set_volume(level: int) -> str:
    """Set system volume (0-100)."""
    level = max(0, min(100, level))
    try:
        subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True)
        return f"Volume set to {level}%."
    except Exception as e:
        return f"Failed to set volume: {e}"
