from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_research_run_writes_versioned_manifest_and_artifacts(tmp_path):
    trades = tmp_path / "xh_demo_trades.jsonl"
    trades.write_text(
        "\n".join([
            '{"day":"2026-01-01","code":"000001.XSHE","strat_ret":0.02,"base_ret":0.01,'
            '"pick_alpha":0.012,"entry_slippage":-0.001,"exit_timing":0.003,'
            '"exposure":0.5,"turnover":0.2,"weight":0.6}',
            '{"day":"2026-01-02","code":"000002.XSHE","strat_ret":0.03,"base_ret":0.01,'
            '"pick_alpha":0.018,"entry_slippage":-0.002,"exit_timing":0.004,'
            '"exposure":0.4,"turnover":0.1,"weight":0.4}',
        ]) + "\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "runs" / "20260103_xh_demo"
    ledger = tmp_path / "HYPOTHESES.jsonl"

    cp = subprocess.run(
        [
            sys.executable,
            "scripts/research_run.py",
            "--trades",
            str(trades),
            "--n-tried",
            "1",
            "--min-days",
            "2",
            "--id",
            "XH-DEMO",
            "--claim",
            "demo claim",
            "--method",
            "demo method",
            "--protocol-id",
            "shortline-demo-v1",
            "--record",
            "--ledger",
            str(ledger),
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    verdict = json.loads(cp.stdout)
    assert verdict["n_trades"] == 2
    assert verdict["diagnostics"]["coverage"]["pick_alpha"] == 2
    assert verdict["diagnostics"]["attribution"]["pick_alpha"]["mean"] == 0.015
    assert verdict["diagnostics"]["exposure"]["exposure"]["max"] == 0.5
    assert verdict["diagnostics"]["turnover"]["turnover"]["sum"] == 0.30000000000000004
    assert verdict["diagnostics"]["concentration"]["code_count"] == 2
    assert (run_dir / "trades.jsonl").read_text(encoding="utf-8") == trades.read_text(encoding="utf-8")
    assert json.loads((run_dir / "verdict.json").read_text(encoding="utf-8")) == verdict

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "20260103_xh_demo"
    assert manifest["hypothesis_id"] == "XH-DEMO"
    assert manifest["protocol_id"] == "shortline-demo-v1"
    assert manifest["parameters"]["n_tried"] == 1
    assert manifest["inputs"]["n_rows"] == 2
    assert len(manifest["inputs"]["trades_sha256"]) == 64
    assert manifest["verdict"]["status"] == verdict["verdict"]
    assert manifest["diagnostics"]["coverage"]["weight"] == 2
    assert manifest["ledger_entry"]["id"] == "XH-DEMO"
    assert json.loads(ledger.read_text(encoding="utf-8").strip())["id"] == "XH-DEMO"
