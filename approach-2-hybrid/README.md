# Approach 2 — Hybrid (Local + Claude API)

**Engine:** Ollama `llama3.1:8b` for simple tasks, Claude API for complex reasoning
**Cost:** Near-free — API only called for hard tasks (~$0.001–0.005/session)
**Status:** 🔜 Coming next

## Plan
- Route simple queries (facts, tasks, memory) to local Ollama
- Route complex reasoning (analysis, code, ambiguous intent) to Claude API
- Smart router that classifies query complexity before dispatching
- Falls back gracefully if API is unavailable
