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

from typing import Any

from xiaocao.mcp import tools


def public_tools():
    """The agent-facing tools with CLEAN signatures.

    The pure functions in tools.py carry an internal ``root: Path`` injection seam
    used only by tests. It MUST NOT be exposed to agents: FastMCP derives a tool's
    input schema from the function signature, so a leaked ``root`` would let a
    caller redirect every file/cache read to an arbitrary directory (read files
    outside the repo, substitute the operating contract). These wrappers drop it,
    so the agent surface is repo-rooted by construction. Order matches TOOLS."""

    def flywheel_status() -> dict[str, Any]:
        return tools.flywheel_status()

    def live_status() -> dict[str, Any]:
        return tools.live_status()

    def data_health_report() -> dict[str, Any]:
        return tools.data_health_report()

    def recent_decisions(n: int = 10) -> list[dict[str, Any]]:
        return tools.recent_decisions(n)

    def ledger_verdicts(n: int = 20) -> list[dict[str, Any]]:
        return tools.ledger_verdicts(n)

    def judge_hypothesis(trades: list, n_tried: int = 1) -> dict[str, Any]:
        return tools.judge_hypothesis(trades, n_tried)

    def operating_contract() -> str:
        return tools.operating_contract()

    wrappers = [
        flywheel_status, live_status, data_health_report, recent_decisions,
        ledger_verdicts, judge_hypothesis, operating_contract,
    ]
    out = []
    for fn in wrappers:
        fn.__doc__ = tools.TOOLS[fn.__name__][1]  # carry the agent-facing description
        out.append((fn.__name__, fn))
    return out


def build_server():  # type: ignore[no-untyped-def]
    """Construct a FastMCP server with every tool registered. Lazily imports the
    SDK so importing this module never requires `mcp`."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("xiaocao")
    for name, fn in public_tools():
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
