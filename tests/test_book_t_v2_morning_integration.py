from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from xiaocao.kol.publication import canonical_sha256


REPO = Path(__file__).resolve().parents[1]
REHEARSAL_DATE = "2026-08-21"


def _write_rehearsal_capsule(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "publications": [],
                "agent_draft": {"themes": [], "status": "pending_observation"},
                "market_validation": {},
                "catalog": {
                    "version": "catalog-integration-rehearsal",
                    "theme_registry": {
                        "version": "registry-integration-rehearsal",
                        "themes": [],
                        "changes": [],
                    },
                    "blocks": [],
                    "etfs": [],
                    "stocks": [],
                },
                "portfolio": {
                    "as_of": REHEARSAL_DATE,
                    "account_equity": 100000,
                    "positions": [],
                    "formal_ledger_mutations": {
                        "positions": 0,
                        "account": 0,
                        "trades": 0,
                    },
                },
                "market_input": {
                    "market_date": REHEARSAL_DATE,
                    "is_trading_day": True,
                    "trading_day_index": 42,
                    "quotes": {},
                    "liquidity": {},
                    "source": "isolated_rehearsal_capsule",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_public_morning_execute_creates_and_consumes_shadow_input_without_ledger_mutation(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(REPO / "scripts/auto_daily.sh", scripts / "auto_daily.sh")
    shutil.copy(REPO / "scripts/book_t_v2_daily.py", scripts / "book_t_v2_daily.py")
    shutil.copy(REPO / "scripts/book_t_shadow.py", scripts / "book_t_shadow.py")
    (scripts / "wait_for_morning_freeze.py").write_text(
        "print('freeze-ready')\n", encoding="utf-8"
    )
    (scripts / "wait_for_agent_reviews.py").write_text(
        "print('review-ready')\n", encoding="utf-8"
    )
    kronos = tmp_path / "kronos_screen" / "scripts"
    kronos.mkdir(parents=True)
    (kronos / "paper_record.py").write_text(
        """
import hashlib, json, sys
from pathlib import Path
root = Path.cwd()
args = sys.argv[1:]
if "--trend-only" not in args:
    raise SystemExit(0)
date = args[args.index("--date") + 1]
live = root / "output" / "live"
semantics = {
    "as_of": date,
    "book": "T",
    "selection": {"as_of": date, "selected_codes": [], "actions": []},
    "actions": [],
    "trade_count": 0,
    "skip_count": 0,
    "position_transition_count": 0,
}
paths = {
    "positions": "output/live/positions.jsonl",
    "account": "output/live/paper_account_T.json",
    "trades": "output/live/paper_trades.jsonl",
}
hashes = {
    name: hashlib.sha256((root / path).read_bytes()).hexdigest()
    for name, path in paths.items()
}
body = {
    "consumer": "book_t_v1_control",
    "producer": "kronos_screen/scripts/paper_record.py",
    "mode": "trend-only",
    "book": "T",
    "as_of": date,
    "artifact_paths": paths,
    "artifact_hashes": hashes,
    "daily_semantics": semantics,
}
try:
    from xiaocao.kol.publication import canonical_sha256
    body["daily_semantics_sha256"] = canonical_sha256(semantics)
    receipt_sha = canonical_sha256(body)
except Exception:
    body["daily_semantics_sha256"] = hashlib.sha256(
        json.dumps(semantics, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    receipt_sha = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
(live / f"book_t_v1_control_receipt_{date}.json").write_text(
    json.dumps({**body, "receipt_sha256": receipt_sha}, sort_keys=True),
    encoding="utf-8",
)
""",
        encoding="utf-8",
    )
    (tmp_path / "output" / "live").mkdir(parents=True)
    (tmp_path / "output" / "live" / "positions.jsonl").write_text(
        "", encoding="utf-8"
    )
    (tmp_path / "output" / "live" / "paper_account_T.json").write_text(
        '{"cash": 100000, "fee_rate": 0.0001}\n', encoding="utf-8"
    )
    (tmp_path / "output" / "live" / "paper_trades.jsonl").write_text(
        "", encoding="utf-8"
    )
    formal_paths = {
        "positions": tmp_path / "output/live/positions.jsonl",
        "account": tmp_path / "output/live/paper_account_T.json",
        "trades": tmp_path / "output/live/paper_trades.jsonl",
    }
    before = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in formal_paths.items()
    }
    capsule = tmp_path / "capsule.json"
    _write_rehearsal_capsule(capsule)
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    real_python = REPO / ".venv/bin/python"
    (venv_bin / "python").write_text(
        f"""#!/bin/sh
if [ "$1" = "-m" ] && [ "$2" = "xiaocao" ] && [ "$3" = "calendar" ]; then
  echo "{REHEARSAL_DATE}"
  exit 0
fi
PYTHONPATH="{REPO / "src"}" exec "{real_python}" "$@"
""",
        encoding="utf-8",
    )
    (venv_bin / "python").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "XIAOCAO_ROOT": str(tmp_path),
            "XIAOCAO_BOOK_T_V2_RUN_MODE": "rehearsal",
            "XIAOCAO_BOOK_T_V2_REHEARSAL_DATE": REHEARSAL_DATE,
            "XIAOCAO_BOOK_T_V2_CAPSULE": str(capsule),
            "XIAOCAO_MORNING_FREEZE_TIMEOUT_SEC": "0",
            "XIAOCAO_AGENT_REVIEW_TIMEOUT_SEC": "0",
        }
    )
    completed = subprocess.run(
        ["bash", "scripts/auto_daily.sh", "morning-execute"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    for name, path in formal_paths.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before[name]
    frozen_path = (
        tmp_path
        / f"output/live/book_t_v2_shadow_input_{REHEARSAL_DATE}.json"
    )
    manifest_path = (
        tmp_path
        / f"output/research/book_t_v2_shadow/{REHEARSAL_DATE}-book-t-v2-shadow/manifest.json"
    )
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert frozen["input_sha256"]
    assert frozen["evidence_lifecycle"]["run_mode"] == "rehearsal"
    assert manifest["formal_ledger_mutations"] == {
        "positions": 0,
        "account": 0,
        "trades": 0,
    }
    assert manifest["verdict"]["status"] == "pending_observation"
    assert "strategy_sample_floor" in manifest["verdict"]["pending_reasons"]
    assert manifest["diagnostics"]["sample"]["real_trading_days"] == 0
