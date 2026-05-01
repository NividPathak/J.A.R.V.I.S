"""Master orchestrator — the central brain of J.A.R.V.I.S."""
import json
from typing import List, Dict, Any, Generator
from config.settings import (
    PROVIDER, SYSTEM_PROMPT, JARVIS_USER,
    OLLAMA_HOST, OLLAMA_MODEL,
    ANTHROPIC_KEY, ANTHROPIC_MODEL,
)

# Tool registry — maps tool names to callables
_TOOLS: Dict[str, Any] = {}


def _register_tools():
    from subsystems import memory, sensors, tasks
    from integrations import web, macos, sports

    return {
        "nba_today": {
            "fn": lambda: sports.nba_today(),
            "description": "Get today's NBA games, scores, and matchups — use for any NBA/basketball question",
            "params": {},
        },
        "nba_standings": {
            "fn": lambda: sports.nba_standings(),
            "description": "Get current NBA standings and playoff picture",
            "params": {},
        },
        "web_search": {
            "fn": lambda q, n=5: web.search(q, n),
            "description": "Search the web for information",
            "params": {"query": "str", "max_results": "int=5"},
        },
        "web_fetch": {
            "fn": lambda url: web.fetch(url),
            "description": "Fetch content from a URL",
            "params": {"url": "str"},
        },
        "news": {
            "fn": lambda topic="technology": web.news(topic),
            "description": "Get latest news on a topic",
            "params": {"topic": "str"},
        },
        "memory_store": {
            "fn": lambda content, category="general", tags="": memory.store(content, category, [t.strip() for t in tags.split(",") if t.strip()]),
            "description": "Store important information in long-term memory",
            "params": {"content": "str", "category": "str=general", "tags": "str="},
        },
        "memory_query": {
            "fn": lambda query: memory.query(query),
            "description": "Search long-term memory for relevant information",
            "params": {"query": "str"},
        },
        "memory_recent": {
            "fn": lambda n=10: memory.get_recent(n),
            "description": "Get recently stored memories",
            "params": {"n": "int=10"},
        },
        "system_status": {
            "fn": lambda: sensors.get_system_status(),
            "description": "Get current system status (CPU, RAM, battery)",
            "params": {},
        },
        "get_time": {
            "fn": lambda: sensors.get_datetime(),
            "description": "Get current date and time",
            "params": {},
        },
        "running_apps": {
            "fn": lambda: sensors.get_running_apps(),
            "description": "Get list of running applications",
            "params": {},
        },
        "clipboard": {
            "fn": lambda: sensors.get_clipboard(),
            "description": "Get current clipboard content",
            "params": {},
        },
        "notify": {
            "fn": lambda title, message, subtitle="": macos.notify(title, message, subtitle),
            "description": "Send a macOS desktop notification",
            "params": {"title": "str", "message": "str", "subtitle": "str="},
        },
        "speak": {
            "fn": lambda text: macos.speak(text),
            "description": "Speak text aloud via macOS text-to-speech",
            "params": {"text": "str"},
        },
        "open_app": {
            "fn": lambda app: macos.open_app(app),
            "description": "Open a macOS application by name",
            "params": {"app_name": "str"},
        },
        "open_url": {
            "fn": lambda url: macos.open_url(url),
            "description": "Open a URL in the default browser",
            "params": {"url": "str"},
        },
        "write_file": {
            "fn": lambda path, content: macos.write_file(path, content),
            "description": "Write content to a file",
            "params": {"path": "str", "content": "str"},
        },
        "read_file": {
            "fn": lambda path: macos.read_file(path),
            "description": "Read content from a file",
            "params": {"path": "str"},
        },
        "set_volume": {
            "fn": lambda level: macos.set_volume(int(level)),
            "description": "Set system volume (0-100)",
            "params": {"level": "int"},
        },
        "add_task": {
            "fn": lambda title, subtasks="", priority="normal": tasks.add_task(title, [s.strip() for s in subtasks.split(",") if s.strip()], priority),
            "description": "Add a task to the task manager",
            "params": {"title": "str", "subtasks": "str=", "priority": "str=normal"},
        },
        "list_tasks": {
            "fn": lambda status="pending": tasks.list_tasks(status),
            "description": "List tasks by status (pending/completed)",
            "params": {"status": "str=pending"},
        },
        "complete_task": {
            "fn": lambda task_id: tasks.complete_task(int(task_id)),
            "description": "Mark a task as complete by ID",
            "params": {"task_id": "int"},
        },
    }


def _tools_prompt(tools: Dict) -> str:
    """Format tools as a system instruction for the LLM."""
    lines = [
        "\nAVAILABLE TOOLS:",
        "You can call tools by responding with JSON in this exact format:",
        '{"tool": "tool_name", "args": {"param": "value"}}',
        "Call ONE tool per response, wait for the result, then continue.",
        "After getting tool results, provide your final answer to the user.",
        "",
    ]
    for name, info in tools.items():
        params = ", ".join(f"{k}: {v}" for k, v in info["params"].items())
        lines.append(f"• {name}({params}) — {info['description']}")
    return "\n".join(lines)


def _parse_tool_call(text: str):
    """Extract tool call JSON from LLM response if present (handles nested braces)."""
    start = text.find('{"tool"')
    if start == -1:
        start = text.find("{'tool'")
    if start == -1:
        return None
    depth = 0
    for i, c in enumerate(text[start:], start):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _execute_tool(tool_name: str, args: Dict, tools: Dict) -> str:
    """Execute a tool and return the result."""
    if tool_name not in tools:
        return f"Unknown tool: {tool_name}"
    try:
        result = tools[tool_name]["fn"](**args)
        return str(result) if result is not None else "Done."
    except Exception as e:
        return f"Tool error ({tool_name}): {e}"


# ── Ollama backend ─────────────────────────────────────────────────────────────

def _ollama_chat(messages: List[Dict], stream: bool = True) -> Generator[str, None, None]:
    """Stream chat from Ollama."""
    try:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST)
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=stream,
        )
        if stream:
            for chunk in response:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
        else:
            yield response.get("message", {}).get("content", "")
    except Exception as e:
        yield f"[Ollama error: {e}]"


# ── Anthropic backend ──────────────────────────────────────────────────────────

def _anthropic_chat(messages: List[Dict], stream: bool = True) -> Generator[str, None, None]:
    """Stream chat from Anthropic Claude."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        # Extract system messages
        system = SYSTEM_PROMPT
        api_msgs = [m for m in messages if m["role"] != "system"]

        kwargs = dict(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system,
            messages=api_msgs,
        )
        if "opus" in ANTHROPIC_MODEL or "sonnet" in ANTHROPIC_MODEL:
            kwargs["thinking"] = {"type": "adaptive"}

        if stream:
            with client.messages.stream(**kwargs) as s:
                for text in s.text_stream:
                    yield text
        else:
            resp = client.messages.create(**kwargs)
            for block in resp.content:
                if block.type == "text":
                    yield block.text
    except Exception as e:
        yield f"[Anthropic error: {e}]"


# ── Unified chat interface ─────────────────────────────────────────────────────

class JARVIS:
    def __init__(self):
        self.tools = _register_tools()
        self.history: List[Dict] = []
        self._build_system_message()

    def _build_system_message(self):
        full_system = SYSTEM_PROMPT + _tools_prompt(self.tools)
        self.system_msg = {"role": "system", "content": full_system}

    def _stream(self, messages: List[Dict]) -> Generator[str, None, None]:
        if PROVIDER == "anthropic":
            yield from _anthropic_chat(messages)
        else:
            yield from _ollama_chat(messages)

    def _get_full_response(self, messages: List[Dict]) -> str:
        return "".join(self._stream(messages))

    def chat(self, user_input: str) -> Generator[str, None, None]:
        """Process user input, handle tool calls, stream the final response."""
        self.history.append({"role": "user", "content": user_input})

        # Build message list with system prompt
        if PROVIDER == "ollama":
            messages = [self.system_msg] + self.history
        else:
            messages = self.history.copy()  # Anthropic takes system separately

        # Agentic loop — handle tool calls
        MAX_TOOL_CALLS = 5
        tool_calls_made = 0

        while tool_calls_made < MAX_TOOL_CALLS:
            response_text = self._get_full_response(messages)
            tool_call = _parse_tool_call(response_text)

            if not tool_call:
                # No tool call — this is the final response
                self.history.append({"role": "assistant", "content": response_text})
                yield from iter(response_text)
                return

            # Execute the tool
            tool_name = tool_call.get("tool", "")
            args = tool_call.get("args", {})

            yield f"\n⚙ [{tool_name}]"

            tool_result = _execute_tool(tool_name, args, self.tools)

            # Add tool exchange to history
            self.history.append({"role": "assistant", "content": response_text})
            self.history.append({
                "role": "user",
                "content": f"[Tool result for {tool_name}]:\n{tool_result}\n\nNow provide your response to the user."
            })

            if PROVIDER == "ollama":
                messages = [self.system_msg] + self.history
            else:
                messages = self.history.copy()

            tool_calls_made += 1

        # Fallback if tool loop maxed out
        response_text = self._get_full_response(messages)
        self.history.append({"role": "assistant", "content": response_text})
        yield from iter(response_text)

    def clear_history(self):
        self.history = []

    def get_provider_info(self) -> str:
        if PROVIDER == "anthropic":
            return f"Anthropic / {ANTHROPIC_MODEL}"
        return f"Ollama / {OLLAMA_MODEL} (local, free)"
