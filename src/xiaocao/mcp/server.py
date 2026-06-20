"""Thin MCP server exposing xiaocao's read + research tools (never live).

Requires the `mcp` SDK (`pip install mcp`); the pure tool functions in tools.py
work without it. Tools are cache/file-only — no live trading, no order
placement, mirroring QuantDinger's MCP safety stance (its MCP intentionally
exposes no live execution).

    pip install mcp
    python3 -m xiaocao.mcp.server          # stdio transport (for Claude Code / Codex)
"""
from __future__ import annotations

import sys

from xiaocao.mcp import tools


def build_server():  # type: ignore[no-untyped-def]
    """Construct a FastMCP server with every tool registered. Lazily imports the
    SDK so importing this module never requires `mcp`."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("xiaocao")
    for name, (fn, _doc) in tools.TOOLS.items():
        server.tool(name=name)(fn)
    return server


def main() -> None:
    try:
        server = build_server()
    except ImportError:
        print(
            "the MCP SDK is not installed. Install it to run the server:\n"
            "    pip install mcp\n"
            "(the pure tools in xiaocao.mcp.tools work without it.)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    server.run()


if __name__ == "__main__":
    main()
