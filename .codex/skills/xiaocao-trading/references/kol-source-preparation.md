# Legacy KOL source-preparation compatibility

This route is retired for production consumers. Historical immutable
`kol-source-preparation` packets and handoff receipts remain readable for audit
and exact reconciliation only; never refresh, rebind or use them as current
semantic input.

The production boundary is the LiangHui publication itself: the remote writer's
validated semantic bundle atomically publishes the report, viewpoints and
initial evaluations, while maintenance appends evaluations and relations.
Trading consumers run:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_trading_context.py projection --cache-only
```

They consume the returned immutable path/hash/counts, then perform one bounded
runtime current-applicability review. They do not reopen unchanged report bodies
or create a second source-notes/opening-draft artifact. Formal decision
publication still loads and verifies only the exact cited reports.
