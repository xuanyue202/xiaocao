"""Pure, cache/file-only tool functions for the xiaocao agent surface.

These delegate to the existing deterministic modules and read accumulated
artifacts — no live API calls, no trading. They return JSON-serializable values
so they can back an MCP server, a CLI, or direct agent use. Every tool here is
safe to call autonomously.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from xiaocao.live import data_health, flywheel, journal, status
from xiaocao.research import guards, ledger

# repo root: src/xiaocao/mcp/tools.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _root(root: Path | None) -> Path:
    return root if root is not None else _REPO_ROOT


def flywheel_status(root: Path | None = None) -> dict[str, Any]:
    """Are the three coupled compounding flywheels wired? ① capital + ② capability
    auto-turn; ③ strategy is an intentional human gate (open/blocked/closed). No network."""
    return flywheel.check_flywheel(root=_root(root), env={})


def live_status(root: Path | None = None) -> dict[str, Any]:
    """The situational-awareness digest: book A vs book B spread, today's
    decisions, open holdings."""
    return status.build_digest(live_dir=_root(root) / "output" / "live")


def data_health_report(root: Path | None = None) -> dict[str, Any]:
    """Dirty-data findings (duplicate snapshots, account drift, stale positions)
    before trusting any A/B verdict."""
    return data_health.check(_root(root) / "output" / "live")


def recent_decisions(n: int = 10, root: Path | None = None) -> list[dict[str, Any]]:
    """The last N structured decision-journal entries (cross-context continuity)."""
    return journal.read_recent(n, path=_root(root) / "output" / "live" / "decision_journal.jsonl")


def ledger_verdicts(n: int = 20, root: Path | None = None) -> list[dict[str, Any]]:
    """The last N research verdicts from the knowledge ledger (what's been tried
    and whether it survived the discipline)."""
    return ledger.read_all(_root(root) / "kronos_screen" / "HYPOTHESES.jsonl")[-n:]


def judge_hypothesis(trades: list[dict[str, Any]], n_tried: int = 1) -> dict[str, Any]:
    """Run a {day, strat_ret, base_ret} results list through the discipline
    guards — the agent cannot launder a day-weighting artifact past this."""
    return guards.evaluate_hypothesis(trades, n_tried=n_tried, cache_only=True)


def operating_contract(root: Path | None = None) -> str:
    """The operating contract (SSOT) text — the agent's law for trading口径,
    staged exits, and the capital-safety boundary."""
    path = _root(root) / "docs" / "OPERATING_CONTRACT.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return f"(operating contract not found at {path})"


# Registry the server iterates over — name -> (callable, one-line description).
TOOLS = {
    "flywheel_status": (flywheel_status, flywheel_status.__doc__),
    "live_status": (live_status, live_status.__doc__),
    "data_health_report": (data_health_report, data_health_report.__doc__),
    "recent_decisions": (recent_decisions, recent_decisions.__doc__),
    "ledger_verdicts": (ledger_verdicts, ledger_verdicts.__doc__),
    "judge_hypothesis": (judge_hypothesis, judge_hypothesis.__doc__),
    "operating_contract": (operating_contract, operating_contract.__doc__),
}
