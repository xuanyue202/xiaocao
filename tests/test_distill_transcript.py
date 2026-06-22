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

    assert dt.ingest(distilled_dir=ddir) == 0
    entries = [json.loads(l) for l in backlog.read_text().splitlines() if l.strip() and not l.startswith("#")]
    # existing + claim A + claim B (the duplicate A is dropped)
    assert [e["id"] for e in entries] == ["XH-005", "XH-006", "XH-007"]
    new = {e["claim"]: e for e in entries if e["id"] != "XH-005"}
    assert set(new) == {"claim A", "claim B"}
    a = new["claim A"]
    assert a["implied_rule"] == "rule A"                       # field mapping
    assert a["operationalization"] == "t"                      # falsifiable_test -> operationalization
    assert a["expected_effect_on_exit_leak"] == "e"            # expected_effect -> ...
    assert a["source_dates"] == ["2026-06-10"]
    assert "authority=0" in a["status"]


def test_ingest_is_idempotent(tmp_path, monkeypatch):
    ddir = tmp_path / "distilled"
    ddir.mkdir()
    (ddir / "2026-06-10_morning.json").write_text(json.dumps(_valid_distilled()), encoding="utf-8")
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text("", encoding="utf-8")
    monkeypatch.setattr(dt, "BACKLOG", backlog)
    dt.ingest(distilled_dir=ddir)
    n1 = len([l for l in backlog.read_text().splitlines() if l.strip()])
    dt.ingest(distilled_dir=ddir)            # second run adds nothing
    n2 = len([l for l in backlog.read_text().splitlines() if l.strip()])
    assert n1 == 1 and n2 == 1
