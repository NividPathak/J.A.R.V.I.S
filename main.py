"""J.A.R.V.I.S — Just A Rather Very Intelligent System"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.columns import Columns
from rich import box
from rich.prompt import Prompt
from rich.markdown import Markdown
import time

from config.settings import JARVIS_NAME, JARVIS_USER, PROVIDER, OLLAMA_MODEL, ANTHROPIC_MODEL
from core.master import JARVIS

console = Console()


BANNER = """
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
"""

COMMANDS = {
    "/clear":   "Clear conversation history",
    "/status":  "Show system status",
    "/memory":  "Show recent memories",
    "/tasks":   "Show pending tasks",
    "/switch":  "Switch model provider",
    "/help":    "Show this help",
    "/exit":    "Exit J.A.R.V.I.S",
}


def show_banner():
    console.print(Text(BANNER, style="bold cyan"))
    provider_str = f"[green]{PROVIDER.upper()}[/] / [cyan]{OLLAMA_MODEL if PROVIDER == 'ollama' else ANTHROPIC_MODEL}[/]"
    console.print(Panel(
        f"[bold white]Just A Rather Very Intelligent System[/]\n"
        f"[dim]User:[/] [yellow]{JARVIS_USER}[/]  |  [dim]Engine:[/] {provider_str}\n"
        f"[dim]Type [bold]/help[/bold] for commands | [bold]/exit[/bold] to quit[/]",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()


def show_help():
    lines = ["[bold cyan]Available Commands:[/]\n"]
    for cmd, desc in COMMANDS.items():
        lines.append(f"  [bold yellow]{cmd:<12}[/] {desc}")
    console.print(Panel("\n".join(lines), border_style="dim", box=box.SIMPLE))


def handle_command(cmd: str, jarvis: JARVIS) -> bool:
    """Handle slash commands. Returns True to continue, False to exit."""
    cmd = cmd.strip().lower()

    if cmd == "/exit":
        console.print("\n[dim cyan]J.A.R.V.I.S offline. Goodbye, sir.[/]")
        return False

    elif cmd == "/clear":
        jarvis.clear_history()
        console.print("[dim]Conversation history cleared.[/]")

    elif cmd == "/status":
        from subsystems.sensors import get_system_status, get_datetime, get_running_apps
        console.print(Panel(
            f"[bold]Time:[/] {get_datetime()}\n"
            f"[bold]System:[/]\n{get_system_status()}\n"
            f"[bold]Apps:[/] {get_running_apps()}",
            title="System Status",
            border_style="cyan",
            box=box.ROUNDED,
        ))

    elif cmd == "/memory":
        from subsystems.memory import get_recent
        console.print(Panel(get_recent(15), title="Recent Memories", border_style="cyan", box=box.ROUNDED))

    elif cmd == "/tasks":
        from subsystems.tasks import list_tasks
        pending = list_tasks("pending")
        console.print(Panel(pending, title="Pending Tasks", border_style="cyan", box=box.ROUNDED))

    elif cmd == "/help":
        show_help()

    elif cmd == "/switch":
        console.print("[yellow]Edit .env file to change JARVIS_PROVIDER and restart.[/]")
        console.print(f"  Current: [cyan]{PROVIDER}[/]")
        console.print("  Options: [green]ollama[/] (free local) | [yellow]anthropic[/] (paid cloud)")

    else:
        console.print(f"[red]Unknown command: {cmd}[/] — type [bold]/help[/] for options")

    return True


def stream_response(jarvis: JARVIS, user_input: str):
    """Stream JARVIS response with live rendering."""
    console.print()

    # Show thinking indicator
    with console.status("[dim cyan]Processing...[/]", spinner="dots"):
        # Collect tokens
        full_response = ""
        tool_lines = []
        main_text = ""

        generator = jarvis.chat(user_input)
        for chunk in generator:
            if chunk.startswith("\n⚙"):
                tool_lines.append(chunk.strip())
            else:
                main_text += chunk
            full_response += chunk

    # Print tool calls dimly
    for tool_line in tool_lines:
        console.print(f"  [dim]{tool_line}[/]")

    # Print the final response
    if main_text.strip():
        console.print()
        console.print(Panel(
            Markdown(main_text.strip()),
            title=f"[bold cyan]{JARVIS_NAME}[/]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        ))
    console.print()


def main():
    show_banner()

    # Check Ollama availability
    if PROVIDER == "ollama":
        try:
            import ollama
            client = ollama.Client(host=__import__("config.settings", fromlist=["OLLAMA_HOST"]).OLLAMA_HOST)
            models = client.list()
            model_names = [m.get("model", m.get("name", "")) for m in models.get("models", [])]
            from config.settings import OLLAMA_MODEL
            if not any(OLLAMA_MODEL in m for m in model_names):
                console.print(f"[yellow]Model [bold]{OLLAMA_MODEL}[/bold] not found locally.[/]")
                console.print(f"[dim]Run: [bold]ollama pull {OLLAMA_MODEL}[/bold] then restart[/]")
                console.print(f"[dim]Available models: {', '.join(model_names) or 'none'}[/]")
                console.print()
        except Exception as e:
            console.print(f"[red]Ollama not reachable: {e}[/]")
            console.print("[dim]Make sure Ollama is running: [bold]brew services start ollama[/bold][/]")
            console.print()

    jarvis = JARVIS()
    console.print(f"[dim cyan]J.A.R.V.I.S online. Ready, {JARVIS_USER}.[/]\n")

    while True:
        try:
            user_input = Prompt.ask(f"[bold yellow]{JARVIS_USER}[/]")

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                if not handle_command(user_input, jarvis):
                    break
                continue

            stream_response(jarvis, user_input)

        except KeyboardInterrupt:
            console.print("\n[dim cyan]J.A.R.V.I.S offline. Goodbye, sir.[/]")
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
