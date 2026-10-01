"""Read-only observation entrypoint; no workflow, API or APP execution."""
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/observe_weekly_evidence.py"


def run(source, output):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(source),
                           "--date", "2026-10-01", "--output", str(output)],
                          capture_output=True, text=True, timeout=10)


def test_observe_captures_existing_legacy_source_without_changing_it(tmp_path):
    source = tmp_path / "source"
    ledger = source / "kronos_screen/HYPOTHESES.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"id": "old-rejection", "ts": "2026-07-10T20:17:02",
                                  "verdict": "REJECTED"}) + "\n")
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    output = tmp_path / "observations/current.json"
    completed = run(source, output)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text())
    assert report["status"] == "insufficient_evidence"
    assert report["hypotheses"][0]["recorded_verdict"] == "REJECTED"
    assert report["production_observations"]["books"]["B"]["closed_cash_net_change"] is None
    assert output.with_suffix(".md").exists()
    assert report["snapshot_manifest_path"]
    after = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert before == after


def test_observe_refuses_artifact_inside_read_only_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    completed = run(source, source / "observation.json")
    assert completed.returncode == 2
    assert list(source.iterdir()) == []


def test_observe_refuses_non_json_output_before_capture(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "observation.md"
    completed = run(source, output)
    assert completed.returncode == 2
    assert not output.exists()
