"""Distill bridge — turn a systematically-wrong calibration result into a falsifiable
CANDIDATE hypothesis, staged for the human gate.

This is the programmatic line from the calibration sensors (posture / exit) to the
research layer, so a flagged rule becomes visible, actionable work instead of a number
that rots in a log. It deliberately does NOT promote into the tracked candidate backlog
(`reference/experience/xiaocao_hypotheses.jsonl` stays human-curated with stable XH ids)
and it does NOT touch the spine: it appends machine-proposed candidates to a RUNTIME
staging file that the eod report and the flywheel self-check surface. A human promotes a
staged candidate into the backlog, where `research_exit_priors.py` / `research_run.py`
must give a PASS and the §10 gate must approve before anything changes a param.
Authority over the deterministic spine = 0 until then.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Callable, Sequence

THRESHOLD = 0.45  # hit-rate below this over enough samples = systematically wrong


def flagged(scored: Sequence[dict], *, key: Callable[[dict], object], min_n: int,
            threshold: float = THRESHOLD) -> list[dict]:
    """Group scored decisions by ``key(record)`` and return the groups that are
    systematically wrong: hit-rate < ``threshold`` over n >= ``min_n``. ``key`` returns a
    hashable label, or None to skip a record. Records without a boolean ``right`` are
    ignored (open windows / non-directional)."""
    agg: dict[object, list[int]] = defaultdict(lambda: [0, 0])
    for s in scored:
        if s.get("right") is None:
            continue
        k = key(s)
        if k is None:
            continue
        agg[k][0] += 1 if s["right"] else 0
        agg[k][1] += 1
    out = []
    for k, (hit, n) in agg.items():
        if n >= min_n and hit / n < threshold:
            out.append({"key": k, "hit": hit, "n": n, "rate": round(hit / n, 3)})
    return sorted(out, key=lambda d: d["rate"])


def stage(path: str | Path, candidates: Sequence[dict]) -> int:
    """Idempotently append candidate records to the runtime staging file, deduped by
    their ``cand_key``. Returns the number newly added (0 if all already present)."""
    path = Path(path)
    existing = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                existing.add(json.loads(line).get("cand_key"))
    added = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for c in candidates:
            if c.get("cand_key") in existing:
                continue
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
            existing.add(c.get("cand_key"))
            added += 1
    return added
