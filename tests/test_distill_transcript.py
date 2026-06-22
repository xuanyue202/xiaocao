"""Tests for the distillation harness (scripts/distill_transcript.py): schema
validation fail-closed, and deterministic hypotheses -> backlog ingest (dedup + ids).
The agent does the reading; these cover only the mechanical guard/plumbing steps."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("distill_transcript", ROOT / "scripts" / "distill_transcript.py")
dt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dt)


def _valid_distilled(date="2026-06-10", kind="morning"):
    return {
        "date": date, "kind": kind, "summary": "s", "directions": [], "stocks": [],
        "method_principles": [], "exit_lessons": [], "decision_trace": [],
        "judgment_heuristics": [], "timing_notes": [], "typo_corrections": [],
        "regime_call": {"horizon": "h", "what_would_falsify": "w"},
        "posture": {"regime": "divergence", "dominant_style": "d", "risk": "r", "style_ranking": []},
        "hypotheses": [
            {"claim": "claim A", "implied_rule": "rule A", "expected_effect": "e", "falsifiable_test": "t"},
        ],
    }


# --- validate ---------------------------------------------------------------

def test_validate_good_distilled(tmp_path):
    f = tmp_path / "2026-06-10_morning.json"
    f.write_text(json.dumps(_valid_distilled()), encoding="utf-8")
    assert dt.validate(f) == 0


def test_validate_missing_keys_fails_closed(tmp_path):
    d = _valid_distilled()
    del d["exit_lessons"]
    f = tmp_path / "x.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    assert dt.validate(f) == 1


def test_validate_freetext_kind_ok_but_bad_date_fails(tmp_path):
    # kind is free-text Chinese in real data — a non-empty string is fine ...
    f = tmp_path / "x.json"
    f.write_text(json.dumps(_valid_distilled(kind="盘后复盘/大师班专场")), encoding="utf-8")
    assert dt.validate(f) == 0
    # ... but an empty kind, or a non-ISO date, fails closed
    f.write_text(json.dumps(_valid_distilled(kind="")), encoding="utf-8")
    assert dt.validate(f) == 1
    f.write_text(json.dumps(_valid_distilled(date="20260610")), encoding="utf-8")
    assert dt.validate(f) == 1


def test_validate_bad_hypothesis_shape(tmp_path):
    d = _valid_distilled()
    d["hypotheses"] = [{"claim": "only a claim"}]  # missing implied_rule/expected_effect/falsifiable_test
    f = tmp_path / "x.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    assert dt.validate(f) == 1


def test_validate_posture_current(tmp_path):
    f = tmp_path / "posture_current.json"
    f.write_text(json.dumps({"as_of": "2026-06-10", "valid_until": "2026-06-15",
                             "regime": "x", "dominant_style": "y", "style_ranking": []}), encoding="utf-8")
    assert dt.validate(f) == 0
    f.write_text(json.dumps({"as_of": "2026-06-10"}), encoding="utf-8")  # missing keys
    assert dt.validate(f) == 1


def test_validate_invalid_json_and_unknown_schema(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{not json", encoding="utf-8")
    assert dt.validate(f) == 1
    f.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    assert dt.validate(f) == 1


# --- ingest -----------------------------------------------------------------

def test_ingest_maps_dedups_and_assigns_ids(tmp_path, monkeypatch):
    ddir = tmp_path / "distilled"
    ddir.mkdir()
    (ddir / "2026-06-10_morning.json").write_text(json.dumps(_valid_distilled()), encoding="utf-8")
    d2 = _valid_distilled(date="2026-06-11")
    d2["hypotheses"] = [
        {"claim": "claim A", "implied_rule": "r", "expected_effect": "e", "falsifiable_test": "t"},  # dup of A
        {"claim": "claim B", "implied_rule": "rB", "expected_effect": "eB", "falsifiable_test": "tB"},
    ]
    (ddir / "2026-06-11_review.json").write_text(json.dumps({**d2, "kind": "review"}), encoding="utf-8")

    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text("# comment header\n" + json.dumps({"id": "XH-005", "claim": "existing"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(dt, "BACKLOG", backlog)

    assert dt.ingest(ddir) == 0          # a directory == bulk backfill
    entries = [json.loads(l) for l in backlog.read_text().splitlines() if l.strip() and not l.startswith("#")]
    # existing + claim A + claim B (the duplicate A is dropped)
    assert [e["id"] for e in entries] == ["XH-005", "XH-006", "XH-007"]
    new = {e["claim"]: e for e in entries if e["id"] != "XH-005"}
    assert set(new) == {"claim A", "claim B"}
    a = new["claim A"]
    assert a["implied_rule"] == "rule A"                       # field mapping
    assert a["operationalization"] == "t"                      # falsifiable_test -> operationalization
    assert a["expected_effect_on_exit_leak"] == "e"            # expected_effect -> ...
    # recurrence-merge: the dup of claim A (in the 06-11 file) is NOT dropped — its date
    # is appended to the existing entry's source_dates (no new id allocated).
    assert a["source_dates"] == ["2026-06-10", "2026-06-11"]
    assert "authority=0" in a["status"]


def test_ingest_recurrence_merges_dates_no_new_id(tmp_path, monkeypatch):
    # a claim repeated across transcripts must MERGE into the existing entry (append the
    # date to source_dates), not allocate a new id. Recurrence = len(source_dates).
    ddir = tmp_path / "distilled"
    ddir.mkdir()
    d1 = _valid_distilled(date="2026-06-10")
    d1["hypotheses"] = [{"claim": "主线被动反弹是减仓信号。", "implied_rule": "r",
                         "expected_effect": "e", "falsifiable_test": "t"}]
    (ddir / "2026-06-10_morning.json").write_text(json.dumps(d1), encoding="utf-8")
    # same claim, different whitespace/punctuation -> must normalize-match and merge
    d2 = _valid_distilled(date="2026-06-22")
    d2["hypotheses"] = [{"claim": "主线被动反弹 是减仓信号", "implied_rule": "r2",
                         "expected_effect": "e2", "falsifiable_test": "t2"}]
    (ddir / "2026-06-22_review.json").write_text(json.dumps(d2), encoding="utf-8")

    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text("# header comment kept\n", encoding="utf-8")
    monkeypatch.setattr(dt, "BACKLOG", backlog)

    dt.ingest(ddir / "2026-06-10_morning.json")
    dt.ingest(ddir / "2026-06-22_review.json")
    lines = backlog.read_text().splitlines()
    assert lines[0] == "# header comment kept"                 # comment header preserved
    entries = [json.loads(l) for l in lines if l.strip() and not l.startswith("#")]
    assert len(entries) == 1                                   # ONE entry, not two
    assert entries[0]["id"] == "XH-001"
    assert entries[0]["source_dates"] == ["2026-06-10", "2026-06-22"]  # recurrence=2


def test_ingest_is_idempotent(tmp_path, monkeypatch):
    ddir = tmp_path / "distilled"
    ddir.mkdir()
    (ddir / "2026-06-10_morning.json").write_text(json.dumps(_valid_distilled()), encoding="utf-8")
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text("", encoding="utf-8")
    monkeypatch.setattr(dt, "BACKLOG", backlog)
    dt.ingest(ddir)
    n1 = len([l for l in backlog.read_text().splitlines() if l.strip()])
    dt.ingest(ddir)                          # second run adds nothing
    n2 = len([l for l in backlog.read_text().splitlines() if l.strip()])
    assert n1 == 1 and n2 == 1


def test_ingest_single_file_only_adds_that_files_hypotheses(tmp_path, monkeypatch):
    # the per-transcript default: --ingest FILE must add ONLY that file's hypotheses,
    # never the whole distilled/ history (the bug the diff-gate caught).
    ddir = tmp_path / "distilled"
    ddir.mkdir()
    (ddir / "2026-06-10_morning.json").write_text(json.dumps(_valid_distilled()), encoding="utf-8")
    today = _valid_distilled(date="2026-06-22")
    today["hypotheses"] = [{"claim": "today only", "implied_rule": "r", "expected_effect": "e",
                            "falsifiable_test": "t"}]
    today_f = ddir / "2026-06-22_morning.json"
    today_f.write_text(json.dumps(today), encoding="utf-8")
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text("", encoding="utf-8")
    monkeypatch.setattr(dt, "BACKLOG", backlog)

    dt.ingest(today_f)                       # one file -> one hypothesis, not both files
    claims = [json.loads(l)["claim"] for l in backlog.read_text().splitlines() if l.strip()]
    assert claims == ["today only"]


# --- retirement / reconcile / reality-check (#5) -----------------------------

def _backlog(tmp_path, monkeypatch, entries):
    p = tmp_path / "backlog.jsonl"
    p.write_text("# header\n" + "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
                 encoding="utf-8")
    monkeypatch.setattr(dt, "BACKLOG", p)
    return p


def test_retire_marks_candidate_and_is_idempotent(tmp_path, monkeypatch):
    p = _backlog(tmp_path, monkeypatch, [
        {"id": "XH-027", "claim": "c1", "source_dates": ["2026-06-22"], "status": "candidate (distilled ...)"},
        {"id": "XH-028", "claim": "c2", "source_dates": ["2026-06-22"], "status": "candidate"},
    ])
    dt.retire(["XH-027"], "复盘证伪:次日主线重新主动领涨", on_date="2026-06-25")
    e = {x["id"]: x for x in (json.loads(l) for l in p.read_text().splitlines()
                              if l.strip() and not l.startswith("#"))}
    assert e["XH-027"]["retired_on"] == "2026-06-25"
    assert "复盘证伪" in e["XH-027"]["retire_reason"]
    assert e["XH-027"]["status"].startswith("retired (2026-06-25)")
    assert "retired_on" not in e["XH-028"]                    # untouched
    dt.retire(["XH-027"], "different reason", on_date="2026-07-01")  # idempotent: keeps first date
    e2 = {x["id"]: x for x in (json.loads(l) for l in p.read_text().splitlines()
                               if l.strip() and not l.startswith("#"))}
    assert e2["XH-027"]["retired_on"] == "2026-06-25"


def test_reconcile_retires_rejected_tags_pass(tmp_path, monkeypatch):
    p = _backlog(tmp_path, monkeypatch, [
        {"id": "XH-011", "claim": "rejected one", "source_dates": ["2026-06-10"], "status": "candidate"},
        {"id": "XH-099", "claim": "passed one", "source_dates": ["2026-06-11"], "status": "candidate"},
        {"id": "XH-100", "claim": "untouched", "source_dates": ["2026-06-12"], "status": "candidate"},
    ])
    ledger = tmp_path / "HYPOTHESES.jsonl"
    ledger.write_text("\n".join(json.dumps(x) for x in [
        {"id": "XH-011", "verdict": "REJECTED"}, {"id": "XH-099", "verdict": "PASS"},
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(dt, "LEDGER", ledger)

    dt.reconcile(on_date="2026-06-25", ledger=ledger)
    e = {x["id"]: x for x in (json.loads(l) for l in p.read_text().splitlines()
                              if l.strip() and not l.startswith("#"))}
    assert e["XH-011"]["retired_on"] == "2026-06-25" and e["XH-011"]["last_verdict"] == "REJECTED"
    assert e["XH-099"]["last_verdict"] == "PASS" and "retired_on" not in e["XH-099"]  # PASS NOT auto-retired
    assert "last_verdict" not in e["XH-100"]                  # not in ledger -> untouched


def test_reality_check_extracts_loop_grades_and_dedups(tmp_path, monkeypatch):
    rc = tmp_path / "reality_checks.jsonl"
    monkeypatch.setattr(dt, "REALITY_CHECKS", rc)
    d = _valid_distilled(date="2026-06-22", kind="盘后复盘")
    d["judgment_heuristics"] = ["if x then y", "【loop】6/22实测:先验方向被确认"]
    d["exit_lessons"] = ["【现实校准·loop核心】晨判被同日修正为减一半", "ordinary lesson"]
    f = tmp_path / "2026-06-22_review.json"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    dt.reality_check(f)
    rows = [json.loads(l) for l in rc.read_text().splitlines() if l.strip()]
    assert len(rows) == 2 and all(r["date"] == "2026-06-22" for r in rows)
    assert any("【loop】" in r["text"] for r in rows) and any("现实校准" in r["text"] for r in rows)
    dt.reality_check(f)                                       # idempotent (deduped by date+text)
    assert len([l for l in rc.read_text().splitlines() if l.strip()]) == 2
