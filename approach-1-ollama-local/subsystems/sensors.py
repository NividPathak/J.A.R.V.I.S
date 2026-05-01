"""Real-world data collection — time, system state, web."""
import datetime
import platform
import subprocess
import psutil


def get_system_status() -> str:
    """Get current system status: CPU, memory, battery, running apps."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    mem_used = mem.used / 1024**3
    mem_total = mem.total / 1024**3

    lines = [
        f"CPU: {cpu:.1f}%",
        f"Memory: {mem_used:.1f}/{mem_total:.1f} GB ({mem.percent}%)",
    ]

    battery = psutil.sensors_battery()
    if battery:
        status = "charging" if battery.power_plugged else "on battery"
        lines.append(f"Battery: {battery.percent:.0f}% ({status})")

    return "\n".join(lines)


def get_datetime() -> str:
    """Get current date and time."""
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y — %I:%M %p")


def get_running_apps() -> str:
    """Get list of currently running applications (macOS)."""
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of (processes where background only is false)'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            apps = [a.strip() for a in result.stdout.strip().split(",") if a.strip()]
            return ", ".join(apps[:20])
    except Exception:
        pass
    return "Unable to retrieve running apps."


def get_clipboard() -> str:
    """Get current clipboard content (macOS)."""
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
        content = result.stdout.strip()
        if content:
            return content[:500] + ("..." if len(content) > 500 else "")
        return "(clipboard is empty)"
    except Exception:
        return "Unable to read clipboard."
