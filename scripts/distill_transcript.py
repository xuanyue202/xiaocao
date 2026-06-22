#!/usr/bin/env python3
"""Distillation harness — the deterministic plumbing around the AGENT-driven
distillation of a 小草 盘前/盘后 transcript into the knowledge layer.

The agent (the `xiaocao-distill` skill) is the entry point and does the READING —
turning Chinese livestream commentary into a structured distilled JSON is inherently
a judgment task, not a script. This harness does ONLY the mechanical, judgment-free
steps the agent calls:

  --feedback            surface what REALITY has falsified (current posture +
                        flagged calibration candidates + recent playbook [校准]
                        lines), so the new distillation sharpens priors that scored
                        wrong. This is the step that makes it a LOOP, not a one-way
                        pipe.
  --validate <file>     schema-check a distilled JSON (or posture_current.json),
                        fail-closed (exit 1) so a malformed distillation never
                        reaches the knowledge layer.
  --ingest              feed the `hypotheses` extracted in distilled/*.json into the
                        candidate backlog (reference/experience/xiaocao_hypotheses.jsonl)
                        with dedup + stable XH ids. Mechanical field-mapping only.

It NEVER reads a transcript, NEVER makes a judgment, NEVER updates posture_current
(that is a synthesized prior the agent writes — the harness only validates it), and
NEVER touches the deterministic spine. Every ingested hypothesis enters authority=0
and must clear research_exit_priors / research_run + the §10 human gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISTILLED = ROOT / "reference" / "experience" / "distilled"
BACKLOG = ROOT / "reference" / "experience" / "xiaocao_hypotheses.jsonl"
POSTURE = ROOT / "reference" / "experience" / "posture_current.json"
PLAYBOOK = ROOT / "docs" / "XIAOCAO_PLAYBOOK.md"
CANDIDATES = ROOT / "output" / "live" / "calibration_candidates.jsonl"

# --- schemas (the contract the agent's distilled JSON must satisfy) ---------- #
# REQUIRED = the 12 keys present in all 23 real distillations (fail-closed).
DISTILLED_KEYS = {
    "date", "kind", "summary", "posture", "regime_call", "directions", "stocks",
    "method_principles", "exit_lessons", "hypotheses", "timing_notes", "typo_corrections",
}
# EXPECTED = high-value but a short/临时加播 session may legitimately lack them — WARN,
# don't reject. decision_trace (the 可反推判断逻辑) is the most valuable field.
DISTILLED_EXPECTED = {"decision_trace", "judgment_heuristics"}
POSTURE_FIELDS = {"regime", "dominant_style", "risk", "style_ranking"}
# `kind` is free-text Chinese (盘前直播 / 盘后复盘 / morning_live / ...); the morning|review
# category lives in the FILENAME, not this field — so only require it be non-empty.
HYP_REQUIRED = {"claim", "implied_rule", "falsifiable_test"}  # expected_effect is optional (114/125)
POSTURE_CURRENT_KEYS = {"as_of", "valid_until", "regime", "dominant_style", "style_ranking"}


def _read_jsonl(path: Path) -> list[dict]:
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


def _norm(claim: str) -> str:
    return re.sub(r"\s+", "", str(claim or ""))


# --- --feedback -------------------------------------------------------------- #
def feedback() -> int:
    print("=== 蒸馏前反馈:现实已经证伪/校准了哪些先验(让这次蒸馏去回应) ===\n")
    if POSTURE.exists():
        p = json.loads(POSTURE.read_text(encoding="utf-8"))
        print(f"现行 posture (as_of {p.get('as_of')}, valid_until {p.get('valid_until')}):")
        print(f"  regime={p.get('regime')}  dominant={p.get('dominant_style','')[:80]}")
        fals = p.get("falsifiers") or []
        for f in fals[:4]:
            print(f"  证伪条件: {str(f)[:100]}")
    else:
        print("(no posture_current.json — no standing prior)")
    print()
    cands = _read_jsonl(CANDIDATES)
    if cands:
        print(f"calibration 已 flag 的先验(<45% 命中,现实说它错了 — 今天口播确认/修正/反驳?):")
        for c in cands:
            print(f"  [{c.get('sensor')}] {c.get('claim','')[:120]}")
    else:
        print("calibration flagged: (none yet — 校准回路还在累积)")
    print()
    if PLAYBOOK.exists():
        cal_lines = [ln for ln in PLAYBOOK.read_text(encoding="utf-8").splitlines() if "[校准" in ln]
        if cal_lines:
            print("playbook 最近的 [校准] 行(现实已改写的先验):")
            for ln in cal_lines[-3:]:
                print(f"  {ln.strip()[:140]}")
    return 0


# --- --validate -------------------------------------------------------------- #
def _validate_distilled(d: dict) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    missing = DISTILLED_KEYS - set(d)
    if missing:
        errs.append(f"missing required top-level keys: {sorted(missing)}")
    missing_expected = DISTILLED_EXPECTED - set(d)
    if missing_expected:
        warns.append(f"missing expected keys {sorted(missing_expected)} "
                     f"(ok for a short/临时加播 session, but decision_trace is the highest-value field)")
    if not isinstance(d.get("kind"), str) or not d.get("kind", "").strip():
        errs.append("kind must be a non-empty string (free-text; morning|review is the filename)")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("date", ""))):
        errs.append(f"date must be ISO YYYY-MM-DD, got {d.get('date')!r}")
    posture = d.get("posture")
    if not isinstance(posture, dict) or (POSTURE_FIELDS - set(posture)):
        errs.append(f"posture must be a dict with {sorted(POSTURE_FIELDS)}")
    hyps = d.get("hypotheses")
    if not isinstance(hyps, list):
        errs.append("hypotheses must be a list")
    else:
        for i, h in enumerate(hyps):
            if not isinstance(h, dict) or (HYP_REQUIRED - set(h)):
                errs.append(f"hypotheses[{i}] must be a dict with {sorted(HYP_REQUIRED)} (expected_effect optional)")
    return errs, warns


def _validate_posture_current(d: dict) -> tuple[list[str], list[str]]:
    missing = POSTURE_CURRENT_KEYS - set(d)
    return ([f"posture_current missing keys: {sorted(missing)}"] if missing else []), []


def validate(path: Path) -> int:
    if not path.exists():
        print(f"⚠ no such file: {path}")
        return 1
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⚠ {path.name}: invalid JSON — {e}")
        return 1
    # detect kind: distilled JSON has 'kind'; posture_current has 'as_of'
    if "kind" in d or "hypotheses" in d:
        errs, warns = _validate_distilled(d)
        label = "distilled"
    elif "as_of" in d:
        errs, warns = _validate_posture_current(d)
        label = "posture_current"
    else:
        print(f"⚠ {path.name}: unrecognized schema (neither distilled nor posture_current)")
        return 1
    for w in warns:
        print(f"  ⚠ {path.name}: {w}")
    if errs:
        print(f"✗ {path.name} ({label}) FAILED schema validation:")
        for e in errs:
            print(f"    - {e}")
        return 1
    print(f"✓ {path.name} ({label}) valid")
    if label == "distilled":
        name = path.name.lower()
        if "morning" in name:
            print("  · 早盘 emphasis: go deep on decision_trace (real-time 观察→推断→动作) + "
                  "regime_call.what_would_falsify (today's forward bet the calibration loop will score)")
        elif "review" in name:
            print("  · 复盘 emphasis: go deep on exit_lessons/method_principles + the prior-check "
                  "(现实确认/证伪了哪条 --feedback 先验) — the most direct nutrient for the loop")
    return 0


# --- --ingest ---------------------------------------------------------------- #
def _next_id(existing: list[dict]) -> int:
    nums = [int(m.group(1)) for e in existing
            if (m := re.fullmatch(r"XH-(\d+)", str(e.get("id", ""))))]
    return (max(nums) + 1) if nums else 1


def ingest(distilled_dir: Path = DISTILLED) -> int:
    existing = _read_jsonl(BACKLOG)
    seen_claims = {_norm(e.get("claim")) for e in existing}
    nxt = _next_id(existing)
    new_entries = []
    for jf in sorted(distilled_dir.glob("*.json")):
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        date = d.get("date")
        for h in d.get("hypotheses", []):
            if not isinstance(h, dict) or not h.get("claim"):
                continue
            key = _norm(h["claim"])
            if key in seen_claims:
                continue
            seen_claims.add(key)
            entry = {
                "id": f"XH-{nxt:03d}",
                "claim": h["claim"],
                "source_dates": [date] if date else [],
                "category": h.get("category", "uncategorized"),
                "implied_rule": h.get("implied_rule", ""),
                "operationalization": h.get("falsifiable_test", ""),
                "expected_effect_on_exit_leak": h.get("expected_effect", ""),
                "status": f"candidate (distilled {date}; authority=0 — must pass "
                          f"research_exit_priors/research_run + §10 before any param change)",
            }
            new_entries.append(entry)
            nxt += 1
    if new_entries:
        with BACKLOG.open("a", encoding="utf-8") as fh:
            for e in new_entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"ingest: +{len(new_entries)} new candidate(s) -> {BACKLOG.name} "
          f"(deduped by claim; ids {f'XH-{nxt-len(new_entries):03d}..XH-{nxt-1:03d}' if new_entries else '—'}). "
          f"Candidates enter authority=0; review the git diff, then they must clear the guards + §10.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feedback", action="store_true", help="surface what reality falsified (run before distilling)")
    ap.add_argument("--validate", metavar="FILE", help="schema-check a distilled JSON or posture_current.json")
    ap.add_argument("--ingest", action="store_true", help="feed distilled hypotheses into the candidate backlog")
    a = ap.parse_args()
    rc = 0
    if a.feedback:
        rc |= feedback()
    if a.validate:
        rc |= validate(Path(a.validate))
    if a.ingest:
        rc |= ingest()
    if not (a.feedback or a.validate or a.ingest):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
