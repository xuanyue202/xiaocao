#!/usr/bin/env python3
"""Distillation harness — deterministic plumbing around AGENT-driven
distillation of attributed KOL transcripts into the Xiaocao knowledge layer.

The agent (the durable-knowledge branch of `kol-intelligence`) is the entry point and does the READING —
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
  --refresh-action-log  rebuild the lightweight routing index from each distilled
                        file's required action_summary. The per-file JSON remains
                        the SSOT; this is only a generated consumer surface.

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
LEDGER = ROOT / "kronos_screen" / "HYPOTHESES.jsonl"          # research verdicts (untracked)
REALITY_CHECKS = ROOT / "output" / "live" / "reality_checks.jsonl"  # loop self-grades (runtime)
ACTION_LOG = ROOT / "reference" / "experience" / "distill_action_log.jsonl"

# --- schemas (the contract the agent's distilled JSON must satisfy) ---------- #
# REQUIRED = the 12 keys present in all 23 real distillations (fail-closed).
DISTILLED_KEYS = {
    "date", "kind", "summary", "posture", "regime_call", "directions", "stocks",
    "method_principles", "exit_lessons", "hypotheses", "timing_notes", "typo_corrections",
    "action_summary",
}
# EXPECTED = high-value but a short/临时加播 session may legitimately lack them — WARN,
# don't reject. decision_trace (the 可反推判断逻辑) is the most valuable field.
DISTILLED_EXPECTED = {"decision_trace", "judgment_heuristics"}
POSTURE_FIELDS = {"regime", "dominant_style", "risk", "style_ranking"}
# `kind` is free-text Chinese (盘前直播 / 盘后复盘 / morning_live / ...); the morning|review
# category lives in the FILENAME, not this field — so only require it be non-empty.
HYP_REQUIRED = {"claim", "implied_rule", "falsifiable_test"}  # expected_effect is optional (114/125)
POSTURE_CURRENT_KEYS = {"as_of", "valid_until", "regime", "dominant_style", "style_ranking"}
ACTION_SUMMARY_FIELDS = {
    "posture_update",
    "playbook_update",
    "hypothesis_update",
    "audit_evidence",
    "instrumentation_todo",
    "routing",
}
PROVENANCE_FIELDS = {"author", "source", "evidence"}


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


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# punctuation stripped before claim-dedup so "评分≥50。" == "评分≥50" == "评分 ≥ 50"
# (normalized-EXACT match only — semantic near-duplicates are intentionally NOT auto-merged;
# that is the agent's judgment at distill time, where --feedback shows the standing claims).
_DEDUP_PUNCT = "，,。.；;：:、'\"“”‘’（）()【】[]｛｝{}！!？?·…~～—-_/\\|　"


def _norm(claim: str) -> str:
    s = re.sub(r"\s+", "", str(claim or ""))
    return s.translate(str.maketrans("", "", _DEDUP_PUNCT)).lower()


def _load_backlog(path: Path) -> list[dict]:
    """Ordered items preserving the file exactly: each is {'raw': line} for a
    comment/blank line or {'entry': dict} for a JSON record. Lets ingest mutate
    entries in place (recurrence-merge) and rewrite WITHOUT losing the # header."""
    items: list[dict] = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            items.append({"raw": line})
        else:
            try:
                items.append({"entry": json.loads(s)})
            except json.JSONDecodeError:
                items.append({"raw": line})
    return items


def _write_backlog(path: Path, items: list[dict], new_entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write((it["raw"] if "raw" in it
                      else json.dumps(it["entry"], ensure_ascii=False)) + "\n")
        for e in new_entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


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
    # loop self-grades 小草 made about his OWN prior (from --reality-check) — the human
    # companion to the mechanical sensors; answer in this distillation whether they hold.
    rc = _read_jsonl(REALITY_CHECKS)
    if rc:
        print("\n复盘自评(现实确认/证伪了哪条先验 — 上几场 review 的 loop 自评):")
        for r in rc[-3:]:
            print(f"  [{r.get('date')}] {str(r.get('text',''))[:130]}")
    # backlog liveness — the 'ingest outruns grading' early-warning, in miniature.
    bl = [e for e in _read_jsonl(BACKLOG)]
    if bl:
        retired = sum(1 for e in bl if e.get("retired_on") or str(e.get("status", "")).startswith("retired"))
        untested = [e for e in bl if str(e.get("status", "")).startswith("candidate") and not e.get("retired_on")]
        oldest = min((min(e.get("source_dates") or ["9999"]) for e in untested), default=None)
        print(f"\ncandidate backlog: {len(bl)} total | {len(untested)} untested | {retired} retired"
              + (f" | oldest untested since {oldest}" if oldest and oldest != '9999' else ""))
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
    action_summary = d.get("action_summary")
    if not isinstance(action_summary, dict):
        errs.append("action_summary must be a dict with the five routing fields + routing")
    else:
        missing_action = ACTION_SUMMARY_FIELDS - set(action_summary)
        if missing_action:
            errs.append(f"action_summary missing keys: {sorted(missing_action)}")
        routing = action_summary.get("routing")
        if routing is not None and (not isinstance(routing, list) or not all(isinstance(x, str) for x in routing)):
            errs.append("action_summary.routing must be a list of strings")
    present_provenance = PROVENANCE_FIELDS.intersection(d)
    if present_provenance and present_provenance != PROVENANCE_FIELDS:
        errs.append(
            "multi-author provenance must include author, source, and evidence together"
        )
    elif present_provenance:
        if not str(d.get("author") or "").strip() or not str(d.get("source") or "").strip():
            errs.append("author and source must be non-empty strings")
        evidence = d.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errs.append("evidence must be a non-empty list")
        else:
            for i, item in enumerate(evidence):
                if (
                    not isinstance(item, dict)
                    or not str(item.get("path") or "").strip()
                    or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256") or ""))
                ):
                    errs.append(
                        f"evidence[{i}] requires path and lowercase 64-char sha256"
                    )
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
            print("  · 早盘 emphasis (delayed, not a live signal): 反推 the pre-open reasoning — go deep on "
                  "decision_trace (观察→推断→动作 + why). Delayed != stale: if the call is still in force "
                  "(within horizon, posture not past valid_until), also extract it as actionable strategy")
        elif "review" in name:
            print("  · 复盘 emphasis: go deep on exit_lessons/method_principles + the prior-check "
                  "(现实确认/证伪了哪条 --feedback 先验) — the most direct nutrient for the loop")
    return 0


# --- --ingest ---------------------------------------------------------------- #
def _next_id(existing: list[dict]) -> int:
    nums = [int(m.group(1)) for e in existing
            if (m := re.fullmatch(r"XH-(\d+)", str(e.get("id", ""))))]
    return (max(nums) + 1) if nums else 1


def ingest(source: Path = DISTILLED) -> int:
    """Feed new candidate hypotheses into the backlog from `source`: a single distilled
    JSON file (the per-transcript default the skill uses), or a directory (bulk backfill,
    only via the explicit --ingest-all — it can dump the whole history into the curated
    backlog).

    Deduped by NORMALIZED claim. A claim that matches an existing entry is NOT dropped:
    its date is appended to that entry's `source_dates` (RECURRENCE-MERGE). Recurrence —
    how many distinct transcripts repeat a claim — is the cheapest compounding signal we
    have (= len(source_dates)); it becomes the natural test-priority for the sweep, so the
    backlog drains by importance instead of accreting near-identical ids. Only a genuinely
    new claim allocates a new XH id."""
    files = sorted(source.glob("*.json")) if source.is_dir() else [source]
    items = _load_backlog(BACKLOG)
    entries = [it["entry"] for it in items if "entry" in it]
    by_claim: dict[str, dict] = {}
    for e in entries:
        by_claim.setdefault(_norm(e.get("claim")), e)   # first occurrence wins the merge target
    nxt = _next_id(entries)
    new_entries: list[dict] = []
    merged = 0

    def source_ref(d: dict, jf: Path) -> dict | None:
        if not PROVENANCE_FIELDS.issubset(d):
            return None
        return {
            "author": d["author"],
            "date": d.get("date"),
            "evidence_sha256": [row["sha256"] for row in d.get("evidence") or []],
            "file": jf.name,
            "source": d["source"],
        }

    for jf in files:
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        date = d.get("date")
        provenance = source_ref(d, jf)
        for h in d.get("hypotheses", []):
            if not isinstance(h, dict) or not h.get("claim"):
                continue
            key = _norm(h["claim"])
            if key in by_claim:                          # recurrence: bump source_dates, no new id
                e = by_claim[key]
                sd = e.setdefault("source_dates", [])
                if date and date not in sd:
                    sd.append(date)
                    sd.sort()
                    merged += 1
                if provenance:
                    refs = e.setdefault("source_refs", [])
                    if provenance not in refs:
                        refs.append(provenance)
                        refs.sort(key=lambda row: (str(row.get("date")), str(row.get("author"))))
                        merged += 1
                    authors = e.setdefault("authors", [])
                    if provenance["author"] not in authors:
                        authors.append(provenance["author"])
                        authors.sort()
                continue
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
            if provenance:
                entry["authors"] = [provenance["author"]]
                entry["source_refs"] = [provenance]
            by_claim[key] = entry
            new_entries.append(entry)
            nxt += 1
    if new_entries or merged:
        _write_backlog(BACKLOG, items, new_entries)
    ids = f"XH-{nxt-len(new_entries):03d}..XH-{nxt-1:03d}" if new_entries else "—"
    print(f"ingest: +{len(new_entries)} new candidate(s), ~{merged} recurrence-merge(s) -> {BACKLOG.name} "
          f"(normalized-claim dedup; new ids {ids}). "
          f"Candidates enter authority=0; review the git diff, then they must clear the guards + §10.")
    return 0


# --- retirement / falsification write-back (close the append-only leaks) ------ #
def _ledger_latest_verdicts(ledger: Path = LEDGER) -> dict[str, str]:
    """Latest research verdict per hypothesis id from the (untracked) verdict ledger."""
    latest: dict[str, str] = {}
    for e in _read_jsonl(ledger):
        hid, v = e.get("id"), e.get("verdict")
        if hid and v:
            latest[str(hid)] = str(v)
    return latest


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def retire(ids: list[str], reason: str, *, on_date: str | None = None) -> int:
    """Mark candidate(s) retired (agent-judgment retirement — e.g. a 复盘 reality-check
    contradicted the claim). Retiring a CANDIDATE (authority=0) only curates the backlog;
    it removes nothing from the spine. Idempotent: re-retiring keeps the first date."""
    on_date = on_date or _today()
    items = _load_backlog(BACKLOG)
    want = set(ids)
    n = 0
    for it in items:
        e = it.get("entry")
        if not e or e.get("id") not in want:
            continue
        if not e.get("retired_on"):
            e["retired_on"] = on_date
            e["retire_reason"] = reason
            if str(e.get("status", "")).startswith("candidate"):
                e["status"] = f"retired ({on_date}): {reason}"
            n += 1
    if n:
        _write_backlog(BACKLOG, items, [])
    print(f"retire: {n} candidate(s) marked retired ({', '.join(sorted(want))}) on {on_date}. "
          f"Backlog curation only — authority over the spine unchanged (was already 0).")
    return 0


def reconcile(*, on_date: str | None = None, ledger: Path = LEDGER) -> int:
    """Evidence-driven retirement: fold the research verdict ledger back into the backlog.
    A candidate whose id has a REJECTED verdict is retired (tape/research killed it — it
    must stop reappearing as live work); a PASS is tagged as human-gate evidence (NOT
    auto-promoted — §10 still decides). Adds structured `last_verdict`/`retired_on` without
    clobbering hand-written status. Idempotent."""
    on_date = on_date or _today()
    verdicts = _ledger_latest_verdicts(ledger)
    items = _load_backlog(BACKLOG)
    retired = passed = tagged = 0
    for it in items:
        e = it.get("entry")
        if not e:
            continue
        v = verdicts.get(str(e.get("id")))
        if not v:
            continue
        if e.get("last_verdict") != v:
            e["last_verdict"] = v
            tagged += 1
        if v == "REJECTED" and not e.get("retired_on"):
            e["retired_on"] = on_date
            e["retire_reason"] = "research_run REJECTED (verdict ledger)"
            if str(e.get("status", "")).startswith("candidate"):
                e["status"] = f"retired ({on_date}): research_run REJECTED"
            retired += 1
        elif v == "PASS":
            passed += 1
    if tagged or retired:
        _write_backlog(BACKLOG, items, [])
    print(f"reconcile: {retired} candidate(s) retired (REJECTED), {passed} PASS tagged as §10 evidence, "
          f"{tagged} verdict(s) folded in from {ledger.name}. PASS is NEVER auto-promoted — human gate decides.")
    return 0


def _loop_grades(d: dict) -> list[str]:
    """The review's self-grades — judgment_heuristics tagged 【loop】 + exit_lessons tagged
    【现实校准. These are 小草 grading his own prior against the tape: the most direct loop
    nutrient, which otherwise only lives in distilled prose."""
    out = []
    for h in d.get("judgment_heuristics", []):
        if isinstance(h, str) and "【loop】" in h:
            out.append(h)
    for ln in d.get("exit_lessons", []):
        if isinstance(ln, str) and "现实校准" in ln:
            out.append(ln)
    return out


def reality_check(path: Path) -> int:
    """Write a distilled review's loop self-grades to a hard surface (reality_checks.jsonl),
    so the 'did the tape confirm/refute the prior?' signal stops dead-ending in prose and
    flows into the next --feedback. Deduped by (date, text)."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠ reality-check: cannot read {path}: {e}")
        return 1
    grades = _loop_grades(d)
    if not grades:
        print(f"reality-check: no 【loop】/现实校准 grades in {path.name} "
              f"(expected in a 复盘; a 盘前/短 session may legitimately have none).")
        return 0
    existing = {(r.get("date"), r.get("text")) for r in _read_jsonl(REALITY_CHECKS)}
    date, kind = d.get("date"), d.get("kind", "")
    added = 0
    REALITY_CHECKS.parent.mkdir(parents=True, exist_ok=True)
    with REALITY_CHECKS.open("a", encoding="utf-8") as fh:
        for g in grades:
            if (date, g) in existing:
                continue
            fh.write(json.dumps({"date": date, "kind": kind, "file": path.name, "text": g},
                                 ensure_ascii=False) + "\n")
            existing.add((date, g))
            added += 1
    print(f"reality-check: +{added} loop self-grade(s) staged from {path.name} -> {REALITY_CHECKS.name} "
          f"(surfaces in the next --feedback).")
    return 0


# --- generated action log --------------------------------------------------- #
def _action_log_record(path: Path, d: dict) -> dict:
    """Compact routing row for consumers. The distilled JSON is the SSOT; this row
    is deliberately lossy so it cannot become a second source of truth."""
    summary = d.get("action_summary") or {}
    record = {
        "date": d.get("date"),
        "kind": d.get("kind"),
        "file": path.name,
        "routing": summary.get("routing", []),
        "posture_update": summary.get("posture_update"),
        "playbook_update": summary.get("playbook_update"),
        "hypothesis_update": summary.get("hypothesis_update"),
        "audit_evidence": summary.get("audit_evidence"),
        "instrumentation_todo": summary.get("instrumentation_todo"),
    }
    if d.get("author"):
        record["author"] = d["author"]
        record["source"] = d.get("source")
    return record


def refresh_action_log(source: Path = DISTILLED, output: Path = ACTION_LOG) -> int:
    """Regenerate the lightweight action-summary index from distilled JSON files.
    Fails closed if any distilled file lacks a valid action_summary; otherwise writes
    deterministic JSONL sorted by filename."""
    files = sorted(source.glob("*.json")) if source.is_dir() else [source]
    records: list[dict] = []
    invalid: list[tuple[Path, list[str]]] = []
    for jf in files:
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            invalid.append((jf, [f"invalid JSON: {e}"]))
            continue
        errs, _warns = _validate_distilled(d)
        if errs:
            invalid.append((jf, errs))
            continue
        records.append(_action_log_record(jf, d))
    if invalid:
        print("refresh-action-log FAILED: invalid distilled file(s)")
        for jf, errs in invalid:
            print(f"  - {jf.name}:")
            for e in errs:
                print(f"      {e}")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"refresh-action-log: wrote {len(records)} row(s) -> {_display_path(output)} "
          "(generated from per-file action_summary; distilled JSON remains SSOT)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feedback", action="store_true", help="surface what reality falsified (run before distilling)")
    ap.add_argument("--validate", metavar="FILE", help="schema-check a distilled JSON or posture_current.json")
    ap.add_argument("--ingest", metavar="FILE", help="feed ONE distilled file's new hypotheses into the candidate backlog")
    ap.add_argument("--ingest-all", action="store_true",
                    help="bulk backfill: ingest ALL distilled files (explicit — can flood the curated backlog)")
    ap.add_argument("--reality-check", metavar="FILE",
                    help="stage a 复盘's 【loop】/现实校准 self-grades to reality_checks.jsonl (surfaces in --feedback)")
    ap.add_argument("--reconcile", action="store_true",
                    help="fold verdict-ledger results back: retire REJECTED candidates, tag PASS as §10 evidence")
    ap.add_argument("--refresh-action-log", action="store_true",
                    help="rebuild reference/experience/distill_action_log.jsonl from required per-file action_summary")
    ap.add_argument("--retire", metavar="ID", action="append",
                    help="retire a candidate by id (agent-judgment retirement; repeatable). Needs --reason")
    ap.add_argument("--reason", help="reason text for --retire")
    a = ap.parse_args()
    rc = 0
    if a.feedback:
        rc |= feedback()
    if a.validate:
        rc |= validate(Path(a.validate))
    if a.ingest:
        rc |= ingest(Path(a.ingest))
    if a.ingest_all:
        rc |= ingest(DISTILLED)
    if a.reality_check:
        rc |= reality_check(Path(a.reality_check))
    if a.reconcile:
        rc |= reconcile()
    if a.refresh_action_log:
        rc |= refresh_action_log()
    if a.retire:
        if not a.reason:
            ap.error("--retire requires --reason")
        rc |= retire(a.retire, a.reason)
    if not (a.feedback or a.validate or a.ingest or a.ingest_all or a.reality_check
            or a.reconcile or a.refresh_action_log or a.retire):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
