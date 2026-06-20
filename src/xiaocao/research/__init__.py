"""xiaocao.research — discipline-enforcing research harness.

Turns the operator's hard-won validation rules (re-derived by hand throughout
kronos_screen/STATE.md) into *executable guardrails*: cache-only, walk-forward
train+test consistency, per-trade (not day-weighted) economics, and
multiple-comparison-aware significance. A hypothesis is reported as validated
ONLY if every guard passes — the harness refuses to launder a day-weighting
artifact (the "+254% cum" trick) into a headline. Verdicts accrue in a
HYPOTHESES.jsonl knowledge ledger so the system never re-litigates a refuted
idea and compounds what it has learned.
"""
