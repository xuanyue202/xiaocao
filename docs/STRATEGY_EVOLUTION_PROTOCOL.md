# Strategy Evolution Protocol

The strategy-evolution protocol is the research governance layer between a candidate hypothesis and a paper/simulation strategy change. It exists to keep automated exploration fast without letting research prose, stale priors, or weak backtests leak into Xiaocao's deterministic trading spine.

## Registry

Machine-readable protocols live in:

```text
reference/experience/research_protocols.yaml
```

Validate the registry with:

```bash
PYTHONPATH=src python3 scripts/strategy_protocols.py --check
```

Each protocol defines:

- the strategy surface it applies to;
- the strategy kernel that must remain stable;
- allowed and forbidden change surfaces;
- the sample unit and guard script;
- required manifest fields and artifacts;
- promotion boundary for `AUTO_APPLIED` versus `PROPOSAL_ONLY`;
- rollback expectation.

## Boundary

Protocols govern research consumption only. They do not block `morning`, `eod`, `live_monitor`, accounting, safety checks, or paper trading surveillance. A missing protocol or manifest should block `AUTO_APPLIED` strategy consumption, not the daily capital loop.

## Current Protocols

- `shortline-book-b-v1`: Book B short-line paper/simulation hypotheses judged by `research_run.py`.
- `trend-book-t-v1`: Book T trend paper/simulation hypotheses judged by `trend_guards.py` / `trend_optimize.py`.

## Research Run Manifest

`scripts/research_run.py --run-dir <dir> --protocol-id <id>` writes:

```text
<dir>/manifest.json
<dir>/trades.jsonl
<dir>/verdict.json
```

The manifest is the durable bridge from "I ran research" to "this result can be consumed." Weekly automation should use the manifest path as evidence, not a loose terminal transcript.

## Non-Negotiables

- Judgment priors and distilled playbook claims remain `authority=0` until they pass the relevant guard.
- A PASS verdict is evidence, not permission to edit the deterministic spine.
- `AUTO_APPLIED` is limited to paper/simulation/research/tooling changes with a complete manifest, evidence bundle, validation, clean target files, and rollback.
- Real-capital, account history, raw data truth sources, fill/stop/accounting, and safety logic require explicit human authorization outside this protocol.
