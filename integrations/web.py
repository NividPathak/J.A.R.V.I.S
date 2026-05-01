"""Web search — Tavily (primary, AI-optimised answers) with DuckDuckGo fallback."""
import httpx
import re
import os

# ── Tavily (primary) ───────────────────────────────────────────────────────────
def _tavily_search(query: str, max_results: int = 5) -> str:
    """Search using Tavily — returns clean answer summaries, not just links."""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,
        )
        lines = []
        if response.get("answer"):
            lines.append(f"Answer: {response['answer']}\n")
        for r in response.get("results", [])[:max_results]:
            lines.append(f"• {r['title']}")
            lines.append(f"  {r.get('content', '')[:250]}\n")
        return "\n".join(lines) if lines else ""
    except Exception:
        return ""


# ── DuckDuckGo (fallback) ──────────────────────────────────────────────────────
def _ddg_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "Web search unavailable — install ddgs: pip install ddgs"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return f"No results found for: {query}"
        lines = [f"Search results for '{query}':\n"]
        for r in results:
            lines.append(f"• {r['title']}")
            lines.append(f"  {r['body'][:250]}\n")
        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


def _ddg_news(topic: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "News search unavailable."
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(topic, max_results=max_results))
        if not results:
            return f"No news found for: {topic}"
        lines = [f"Latest news on '{topic}':\n"]
        for r in results:
            lines.append(f"• {r['title']}")
            lines.append(f"  {r.get('body', '')[:200]}\n")
        return "\n".join(lines)
    except Exception as e:
        return f"News failed: {e}"


# ── Public API ─────────────────────────────────────────────────────────────────

def search(query: str, max_results: int = 5) -> str:
    """Search the web. Uses Tavily (AI-summarised) if key set, else DuckDuckGo."""
    result = _tavily_search(query, max_results)
    if result:
        return result
    return _ddg_search(query, max_results)


def news(topic: str = "technology", max_results: int = 5) -> str:
    """Get latest news — tries Tavily then DuckDuckGo."""
    result = _tavily_search(f"latest news {topic}", max_results)
    if result:
        return result
    return _ddg_news(topic, max_results)


def fetch(url: str, max_chars: int = 3000) -> str:
    """Fetch and extract text from a URL."""
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_chars] + ("..." if len(text) > max_chars else "")
    except Exception as e:
        return f"Failed to fetch {url}: {e}"
