"""Tests for the pure MCP tool functions (src/xiaocao/mcp/tools.py).

These run without the mcp SDK and prove the tool surface is safe (read/research
only) and JSON-shaped.
"""
from __future__ import annotations

import inspect
import json

from xiaocao.mcp import server, tools


def test_server_public_tools_do_not_expose_root_param():
    # Security: the pure tools take an internal `root` injection seam (tests only).
    # FastMCP derives the agent-callable schema from the signature, so leaking
    # `root` would let a caller redirect every file/cache read outside the repo.
    # The server must register clean wrappers that drop it.
    public = dict(server.public_tools())
    assert set(public) == set(tools.TOOLS)  # same surface, just sanitized signatures
    for name, fn in public.items():
        params = inspect.signature(fn).parameters
        assert "root" not in params, f"{name} leaks the internal root param to agents"
        assert fn.__doc__, f"{name} lost its agent-facing description"


def test_tools_registry_complete():
    expected = {
        "flywheel_status", "live_status", "data_health_report", "recent_decisions",
        "ledger_verdicts", "judge_hypothesis", "operating_contract",
    }
    assert set(tools.TOOLS) == expected
    assert all(doc for _fn, doc in tools.TOOLS.values())  # every tool documented


def test_judge_hypothesis_runs_the_guards():
    trades = [{"day": f"2026-01-{i+1:02d}", "strat_ret": 0.01, "base_ret": 0.0} for i in range(10) for _ in range(3)]
    v = tools.judge_hypothesis(trades, n_tried=1)
    assert v["verdict"] in {"PASS", "REJECTED"} and "guards" in v


def test_live_status_and_health_tolerate_empty_root(tmp_path):
    s = tools.live_status(root=tmp_path)
    assert "book_a" in s and "book_b" in s
    h = tools.data_health_report(root=tmp_path)
    assert h["ok"] is True  # nothing to find in an empty tree


def test_flywheel_status_shape(tmp_path):
    r = tools.flywheel_status(root=tmp_path)
    assert "capital_flywheel" in r and "capability_flywheel" in r and "spinning" in r


def test_all_tool_results_are_json_serializable(tmp_path):
    for name in ("flywheel_status", "live_status", "data_health_report"):
        fn = tools.TOOLS[name][0]
        json.dumps(fn(root=tmp_path))  # must not raise
    json.dumps(tools.recent_decisions(root=tmp_path))
    json.dumps(tools.ledger_verdicts(root=tmp_path))
