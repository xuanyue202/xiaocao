"""xiaocao MCP surface — typed, cache/file-only tools an agent operates through.

The thesis endpoint of "agent operates through a typed tool surface, not stdout
scraping". Tools are read + research + situational-awareness only — **never live
trading, never order placement** (mirroring QuantDinger's MCP safety stance). The
pure tool functions live in `tools.py` (no SDK dependency, fully tested); the
optional MCP transport in `server.py` lazily loads the `mcp` SDK.
"""
