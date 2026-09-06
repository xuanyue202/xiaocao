from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.live import kol_policy, paper_decision_support as support


NOW = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
CODES = ["000001.XSHE", "000002.XSHE", "600000.XSHG", "600001.XSHG"]


def publish(root, *, scale=1.0, skips=(), asof=NOW, runtime="paper"):
    decision = {
        "schema_version": "kol-trading-decision.v1", "decision_id": "reviewed-paper-1",
        "agent_id": "reader", "book": "B", "runtime": runtime,
        "as_of": asof.isoformat(), "valid_until": (asof + timedelta(hours=2)).isoformat(),
        "buy_scale": scale, "skip_codes": list(skips), "exit_codes": [],
        "source_refs": [{"report_id": "report-1", "author_id": "xiaocao",
                         "content_sha256": "a" * 64,
                         "source_published_at": (asof - timedelta(hours=1)).isoformat(),
                         "received_at": (asof - timedelta(minutes=1)).isoformat()}],
        "rationale": "Reviewed full-source bounded buy judgment.",
        "invalidation_conditions": ["Review on material evidence change."],
        "current_checks": [{"claim": "Current evidence supports the judgment.",
                            "observed_at": asof.isoformat(), "evidence_ref": "fixture:quote",
                            "verdict": "supports"}],
    }
    review = {"decision_sha256": kol_policy.decision_sha256(decision), "status": "approved",
              "reviewer_agent_id": "independent-reviewer", "reviewed_at": asof.isoformat(),
              "coverage_complete": True, "source_fidelity": True,
              "applicability_checked": True, "counterevidence_checked": True}
    kol_policy.publish_decision(root / "output/live/kol_policy/decisions", decision, review, asof)
    return decision


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    import kronos_screen.scripts.paper_record as pr

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pr, "ROOT", tmp_path)
    live = tmp_path / "output/live"
    live.mkdir(parents=True)
    acct = {"initial_capital": 100000.0, "cash": 100000.0, "realized_pnl": 0.0,
            "fee_rate": 0.0001, "total_fees": 0.0}
    (live / "paper_account.json").write_text(json.dumps(acct))
    (live / "positions.jsonl").write_text("")
    candidates = [{"date": "2026-09-06", "is_live": True, "book": "B", "code": code,
                   "captured_at": "2026-09-06T09:25:00+08:00", "name": code,
                   "mode": f"mode-{index}", "mode_trade_eligible": True,
                   "mode_state": "ACTIVE", "rank_score": 400 - index * 100,
                   "open": 10.0, "basket_price": 10.2}
                  for index, code in enumerate(CODES)]
    # Other books and cold states cannot enter the candidate slots.
    candidates.extend([{**candidates[0], "code": "600099.XSHG", "book": "T", "rank_score": 9999},
                       {**candidates[0], "code": "600088.XSHG", "mode_state": "COLD",
                        "mode_trade_eligible": False, "rank_score": 9998}])
    (live / "signal_snapshots.jsonl").write_text("".join(json.dumps(row) + "\n" for row in candidates))
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(pr, "datetime", Clock)
    monkeypatch.setattr(pr, "XiaocaoClient", lambda: object())
    def fills(_client, picks, *_args, **_kwargs):
        return [{**row, "_paper_fill": {"price": 10.0, "basis": "fixture-window-vwap"}}
                for row in picks], []
    monkeypatch.setattr(pr, "_attach_fill_prices", fills)

    def run(*extra):
        monkeypatch.setattr(sys, "argv", ["paper_record.py", "--date", "2026-09-06",
                                         "--no-wait-fill-window", "--intelligence-trade", "off", *extra])
        pr.main()
        claim = support.read_consumption(tmp_path, "2026-09-06", "mode_exec_star")
        result_path = support.consumption_path(tmp_path, "2026-09-06", "mode_exec_star").with_suffix(".result.json")
        terminal = json.loads(result_path.read_text()) if result_path.exists() else None
        return rows(live / "positions.jsonl"), claim, terminal
    return tmp_path, live, pr, run


def test_no_policy_keeps_normal_allocator_and_exact_ab_pairing(runtime):
    root, live, pr, run = runtime
    frozen = (live / "signal_snapshots.jsonl").read_bytes()
    positions, claim, terminal = run()
    b = [row for row in positions if row["book"] == "B"]
    a = [row for row in positions if row["book"] == "A"]
    assert [row["code"] for row in b] == CODES[:3]
    assert [(r["code"], r["shares"], r["entry_price"]) for r in b] == [
        (r["code"], r["shares"], r["entry_price"]) for r in a]
    assert all(row["shares"] == row["paper_decision_support"]["baseline_shares"] for row in b)
    assert terminal["status"] == "bought" and terminal["buy_count"] == 3
    assert claim["kol_decision"]["status"] == "no_decision"
    assert claim["supporting_health"] == "degraded"
    assert (live / "signal_snapshots.jsonl").read_bytes() == frozen
    assert claim["snapshot_sha256"] == hashlib.sha256(frozen).hexdigest()


@pytest.mark.parametrize("scale", [0, 0.1, 0.5, 1])
def test_kol_scale_and_skipped_slots_leave_cash_without_refill(runtime, scale):
    root, live, pr, run = runtime
    decision = publish(root, scale=scale, skips=[CODES[0]])
    positions, claim, terminal = run()
    b = [row for row in positions if row["book"] == "B"]
    assert CODES[0] not in [row["code"] for row in b]
    assert CODES[3] not in [row["code"] for row in b]
    assert claim["baseline_codes"] == CODES[:3]
    for slot in claim["slots"]:
        expected = 0 if slot["code"] == CODES[0] else int(slot["baseline_shares"] * scale / 100) * 100
        assert slot["final_shares"] == expected
        assert slot["kol_decision_sha256"] == kol_policy.decision_sha256(decision)
    acct = json.loads((live / "paper_account.json").read_text())
    assert acct["cash"] == round(100000 - sum(row["entry_cash_out"] for row in b), 2)
    for row in b:
        assert row["entry_fee"] == round(row["shares"] * 10 * 0.0001, 2)
    assert terminal["buy_count"] == len(b)
    assert len([row for row in positions if row["book"] == "A"]) == len(b)


@pytest.mark.parametrize("age,status", [(timedelta(minutes=16), "needs_refresh"),
                                       (timedelta(hours=3), "expired")])
def test_expired_or_stale_checks_are_neutral_with_decision_id(runtime, age, status):
    root, live, pr, run = runtime
    publish(root, scale=0, skips=CODES, asof=NOW - age)
    positions, claim, terminal = run()
    assert terminal["buy_count"] == 3
    assert claim["kol_decision"]["status"] == status
    assert claim["kol_decision"]["decision_id"] == "reviewed-paper-1"
    assert claim["supporting_health"] == "degraded"
    assert all(slot["final_shares"] == slot["baseline_shares"] for slot in claim["slots"])


def test_live_only_policy_cannot_affect_paper(runtime):
    root, live, pr, run = runtime
    publish(root, scale=0, runtime="live")
    _, claim, result = run()
    assert result["buy_count"] == 3
    assert claim["kol_decision"]["status"] == "no_decision"


def test_malformed_decision_stops_buys_and_audit_has_zero_terminal(runtime):
    root, live, pr, run = runtime
    store = live / "kol_policy/decisions"
    store.mkdir(parents=True)
    (store / "broken.json").write_text("{broken")
    before = (live / "paper_account.json").read_bytes()
    positions, claim, result = run()
    assert positions == [] and result["status"] == "no_buy"
    assert claim["kol_decision"]["status"] == "blocked"
    assert len(claim["slots"]) == 3
    assert (live / "paper_account.json").read_bytes() == before
    assert not (live / "paper_account_A.json").exists()


@pytest.mark.parametrize("pnl,expected", [(-4000, 0.5), (-6000, 0.0)])
def test_original_kill_switch_stays_stricter_and_no_fake_a_trades(runtime, pnl, expected):
    root, live, pr, run = runtime
    sensor = {"book": "A", "code": "600999.XSHG", "entry_date": "2026-09-01",
              "status": "closed", "exit_date": "2026-09-04", "exit_price": 9,
              "entry_cash_out": 100000, "realized_pnl": pnl}
    (live / "positions.jsonl").write_text(json.dumps(sensor) + "\n")
    publish(root, scale=1)
    positions, claim, result = run()
    assert pr._kill_switch_factor()[0] == expected
    assert all(slot["effective_scale"] == expected for slot in claim["slots"])
    assert positions[0] == sensor
    if expected == 0:
        assert positions == [sensor] and result["buy_count"] == 0
        assert not (live / "paper_trades.jsonl").exists()


def test_risk_pause_prevents_new_buys_and_records_consumption(runtime):
    root, live, pr, run = runtime
    path = live / "paper_account.json"
    current = json.loads(path.read_text())
    peak = {**current, "cash": 130000, "realized_pnl": 30000}
    path.write_text(json.dumps(peak))
    support.evaluate_paper_risk(root, peak, [], now=NOW - timedelta(minutes=1), mark_provider=lambda code: {})
    path.write_text(json.dumps(current))
    positions, claim, result = run()
    assert positions == [] and result["buy_count"] == 0
    assert claim["risk_receipt"]["status"] == "PAUSED"
    assert claim["risk_receipt"]["history_basis"] == "since_activation"
    assert len(claim["slots"]) == 3


def test_runtime_does_not_apply_kill_before_the_single_minimum_cap(runtime, monkeypatch):
    root, live, pr, run = runtime
    path = live / "paper_account.json"
    current = json.loads(path.read_text())
    peak = {**current, "cash": 120000, "realized_pnl": 20000}
    path.write_text(json.dumps(peak))
    support.evaluate_paper_risk(root, peak, [], now=NOW - timedelta(minutes=1), mark_provider=lambda code: {})
    path.write_text(json.dumps({**current, "cash": 108000, "realized_pnl": 8000}))
    sensor = {"book": "A", "code": "600999.XSHG", "entry_date": "2026-09-01",
              "status": "closed", "exit_date": "2026-09-04", "exit_price": 9,
              "entry_cash_out": 100000, "realized_pnl": -4000}
    (live / "positions.jsonl").write_text(json.dumps(sensor) + "\n")
    publish(root, scale=0.5)
    allocator = pr.plan_board_lot_orders
    calls = []
    def capture(*args, **kwargs):
        calls.append(kwargs)
        return allocator(*args, **kwargs)
    monkeypatch.setattr(pr, "plan_board_lot_orders", capture)
    _, claim, result = run()
    assert len(calls) == 1
    assert calls[0]["target_scale"] == 1.0
    assert calls[0]["max_batch_ratio"] == 0.5
    assert claim["risk_receipt"]["deploy_factor"] == 0.5
    assert result["buy_count"] == 3
    for slot in claim["slots"]:
        assert slot["kol_scale"] == slot["kill_factor"] == slot["risk_deploy_factor"] == 0.5
        assert slot["effective_scale"] == 0.5
        assert slot["final_shares"] == int(slot["baseline_shares"] * 0.5 / 100) * 100


@pytest.mark.parametrize("bad", ["broken", '{"cash": NaN}', '{"cash": -1}'])
def test_malformed_account_has_blocked_receipt_and_no_buy(runtime, bad):
    root, live, pr, run = runtime
    (live / "paper_account.json").write_text(bad)
    positions, claim, result = run()
    assert positions == [] and result["buy_count"] == 0
    assert claim["risk_receipt"]["status"] == "BLOCKED"
    assert (live / "paper_account.json").read_text() == bad


@pytest.mark.parametrize("zero", [False, True])
def test_duplicate_consumption_does_not_rewrite_even_zero_buy(runtime, zero):
    root, live, pr, run = runtime
    publish(root, scale=0 if zero else 0.5)
    run()
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in live.rglob("*") if path.is_file()}
    run("--allow-additional")
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in live.rglob("*") if path.is_file()}
    assert before == after


def test_interrupted_claim_never_replays_new_writer(runtime, monkeypatch):
    root, live, pr, run = runtime
    publish(root)
    def interrupted(_record):
        raise RuntimeError("simulated interruption after durable claim")
    monkeypatch.setattr(pr, "_append_trade", interrupted)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run()
    before = {path: path.read_bytes() for path in live.rglob("*") if path.is_file()}
    _, claim, terminal = run()
    assert claim["status"] == "claimed" and terminal is None
    assert before == {path: path.read_bytes() for path in live.rglob("*") if path.is_file()}


@pytest.mark.parametrize("kol_scale,risk_factor,kill_factor,expected_scale", [
    (0.5, 0.5, 1.0, 0.5),
    (0.5, 0.5, 0.5, 0.5),
    (0.2, 0.5, 1.0, 0.2),
    (1.0, 0.5, 1.0, 0.5),
    (1.0, 1.0, 0.5, 0.5),
    (1.0, 0.0, 1.0, 0.0),
    (0.5, 0.5, 0.0, 0.0),
])
def test_risk_kill_and_kol_are_one_minimum_cap(tmp_path, kol_scale, risk_factor, kill_factor, expected_scale):
    publish(tmp_path, scale=kol_scale)
    decision = kol_policy.load_decision(tmp_path / "output/live/kol_policy/decisions", "B", "paper", NOW)
    baseline = [{"code": CODES[0], "execution_price": 10.0, "mode_exec_planned_shares": 1600}]
    original = copy.deepcopy(baseline)
    result, audit = support.apply_buy_policy(baseline, decision,
                                            {"deploy_factor": risk_factor, "status": "REDUCED", "receipt_sha256": "a" * 64},
                                            kill_factor=kill_factor, fee_rate=0.0001)
    expected_shares = int(1600 * expected_scale / 100) * 100
    assert audit[0]["final_shares"] == expected_shares
    assert (result[0]["mode_exec_planned_shares"] if result else 0) == expected_shares
    assert audit[0]["effective_scale"] == expected_scale
    assert baseline == original
