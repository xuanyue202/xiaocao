#!/usr/bin/env python3
"""Flywheel sweep — the scheduled CONSUMER of the candidate backlog.

The backlog is an append-only PRODUCER (every distilled transcript adds candidates). Without
a consumer it accretes weight, not intelligence — the long-termism failure mode the retro
named: hundreds of unscored, never-retired priors against a human gate that scales linearly.
This sweep is that consumer, made cadence-independent and prioritized:

  1. RECONCILE the research verdict ledger back into the backlog — retire REJECTED candidates
     (reality killed them, they must stop reappearing as live work) and tag PASS as §10
     evidence. (Delegates to distill_transcript.reconcile.)
  2. RANK the untested candidates by TEST-PRIORITY = (recurrence desc, oldest first), where
     recurrence = how many distinct transcripts repeat the claim (len(source_dates)) — the
     cheapest signal of which prior is worth a researcher's time. Flag which are
     cache-expressible (operationalization runnable on the local cache).
  3. SURFACE any PASS verdict as human-gate evidence, and the scoreboard so the
     ingest-vs-grading gap stays visible.

It NEVER runs research itself (each candidate needs a human-written operationalization that
research_run.py / research_exit_priors.py executes under the train+test guard) and NEVER
promotes anything — authority over the deterministic spine stays 0. It turns 'get smarter'
from a manual sprint into a standing, prioritized queue. Report-only: safe to schedule.

    python3 scripts/flywheel_sweep.py              # reconcile + print the ranked queue
    python3 scripts/flywheel_sweep.py --top 5
    python3 scripts/flywheel_sweep.py --no-reconcile
    python3 scripts/flywheel_sweep.py --json
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import flywheel  # noqa: E402

BACKLOG = ROOT / "reference" / "experience" / "xiaocao_hypotheses.jsonl"
APPLIED_VERDICTS = ROOT / "reference" / "experience" / "applied_verdicts.jsonl"

# tokens that mean "this candidate can be tested on the local cache" (vs needing fresh data
# collection or a human to first write the operationalization)
_CACHE_TOKENS = ("cache", "date_kline", "block_category_rank", "minute_line", "逐笔",
                 "research_run", "research_exit_priors", "walk-forward", "walk_forward")


def _load_distill():
    """Load the distill harness module by path (it's a script, not a package) to reuse its
    reconcile() — single source of truth for ledger→backlog reconciliation."""
    spec = importlib.util.spec_from_file_location("distill_transcript", ROOT / "scripts" / "distill_transcript.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _entries(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            pass
    return out


def _is_retired(e: dict) -> bool:
    return bool(e.get("retired_on")) or str(e.get("status", "")).startswith("retired")


def _is_tested(e: dict) -> bool:
    st = str(e.get("status", ""))
    return (bool(e.get("last_verdict")) or st.startswith(("tested", "SHELVED", "evidence"))
            or _is_retired(e))


def _cache_expressible(e: dict) -> bool:
    op = str(e.get("operationalization", ""))
    return any(tok in op for tok in _CACHE_TOKENS)


def _applied_verdict_ids(path: Path = APPLIED_VERDICTS) -> set[str]:
    """PASS verdicts already consumed by a paper/simulation/tooling actuator."""
    out: set[str] = set()
    for e in _entries(path):
        hid = e.get("id")
        status = str(e.get("status", "applied")).lower()
        if hid and status in {"applied", "consumed"}:
            out.add(str(hid))
    return out


def rank_queue(entries: list[dict], *, today: date | None = None) -> list[dict]:
    """Untested candidates ranked by test-priority: recurrence desc, then oldest first.
    Cache-expressible ones float up within the same recurrence (a researcher can act now)."""
    today = today or date.today()
    out = []
    for e in entries:
        if _is_tested(e) or _is_retired(e):
            continue
        sd = e.get("source_dates") or []
        recurrence = len(sd)
        oldest = min(sd) if sd else None
        age = None
        if oldest:
            try:
                age = (today - date.fromisoformat(oldest)).days
            except (TypeError, ValueError):
                pass
        out.append({
            "id": e.get("id"), "recurrence": recurrence, "oldest": oldest, "age_days": age,
            "category": e.get("category", "?"), "cache_expressible": _cache_expressible(e),
            "claim": str(e.get("claim", ""))[:90], "priority": e.get("priority"),
        })
    # priority = (recurrence desc, cache-expressible first, oldest first, id) — recurrence is
    # the dominant key: a claim 小草 repeats across many transcripts is the strongest signal.
    out.sort(key=lambda r: (-r["recurrence"], not r["cache_expressible"],
                            r["oldest"] or "9999", str(r["id"])))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def pass_evidence(entries: list[dict], *, applied_ids: set[str] | None = None) -> list[str]:
    applied_ids = applied_ids or set()
    return [
        str(e.get("id"))
        for e in entries
        if e.get("last_verdict") == "PASS" and str(e.get("id")) not in applied_ids
    ]


def sweep(*, top: int, reconcile: bool, as_json: bool) -> int:
    if reconcile:
        if as_json:
            with contextlib.redirect_stdout(sys.stderr):
                _load_distill().reconcile()  # retire REJECTED, tag PASS; idempotent
        else:
            _load_distill().reconcile()  # retire REJECTED, tag PASS; idempotent
    entries = _entries(BACKLOG)
    queue = rank_queue(entries)
    passes = pass_evidence(entries, applied_ids=_applied_verdict_ids())
    k = flywheel.knowledge_scoreboard(ROOT)

    if as_json:
        print(json.dumps({"scoreboard": k, "pass_evidence": passes, "queue": queue},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"flywheel sweep — backlog consumer (authority=0; NEVER auto-promotes)\n")
    print(f"scoreboard: {k['candidates_total']} candidates | tested {k['candidates_tested']} "
          f"({k['candidate_to_tested']:.0%}) | retired {k['candidates_retired']} | "
          f"untested {k['candidates_untested']} | PASS {k['candidates_passed']}")
    if passes:
        print(f"\n⚠ PASS verdict(s) — §10 human-gate evidence (apply via params.py is a HUMAN decision): "
              f"{', '.join(passes)}")
    cache_n = sum(1 for r in queue if r["cache_expressible"])
    print(f"\ntest-priority queue ({len(queue)} untested, {cache_n} cache-expressible now) — "
          f"ranked by recurrence↓ then age↑:")
    if not queue:
        print("  (empty — every candidate is tested or retired)")
    for r in queue[:top]:
        tag = "✓cache" if r["cache_expressible"] else "needs-op"
        age = f"{r['age_days']}d" if r["age_days"] is not None else "—"
        print(f"  #{r['rank']:>2} {str(r['id']):<7} rec×{r['recurrence']} age {age:<5} "
              f"[{r['category']:<8}] {tag:<8} {r['claim']}")
    if len(queue) > top:
        print(f"  … +{len(queue) - top} more (raise --top to see)")
    print(f"\nnext: pick a top cache-expressible candidate, write/confirm its operationalization, run "
          f"scripts/research_run.py (or research_exit_priors.py) under the train+test guard; "
          f"a PASS is §10 evidence, never an auto param change.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=10, help="show top N of the priority queue")
    ap.add_argument("--no-reconcile", action="store_true", help="skip folding ledger verdicts back in")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    return sweep(top=a.top, reconcile=not a.no_reconcile, as_json=a.json)


if __name__ == "__main__":
    sys.exit(main())
