from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from xiaocao.live.foundersc_opencli import FounderscQuantOpenCLIAdapter
from xiaocao.live.trading_execution import BrokerStatus, TradePlan


def _plan() -> TradePlan:
    return TradePlan(
        plan_id="plan-opencli",
        strategy_run_id="run",
        snapshot_ref="snapshot#1",
        strategy_sha="sha",
        trade_date="2026-08-15",
        book="B",
        logical_account_id="primary",
        environment="mock",
        code="000001.XSHE",
        name="测试标的",
        side="BUY",
        shares=200,
        limit_price=10.05,
        basket_price=10.10,
        market_guard_status="ok",
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        recovery_deadline=datetime(2026, 8, 15, 1, 45, tzinfo=timezone.utc),
    )


class Runner:
    def __init__(self, row: dict, *, returncode: int = 0):
        self.row = row
        self.returncode = returncode
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(list(command))
        return subprocess.CompletedProcess(
            command,
            self.returncode,
            stdout=json.dumps([self.row], ensure_ascii=False),
            stderr="",
        )


def test_probe_and_prepare_consume_only_template_receipt() -> None:
    runner = Runner({
        "status": "prepared_readback",
        "environment": "mock",
        "logical_account_id": "primary",
        "account_binding": "not_proven",
        "field_readback": {
            "code": "000001",
            "side": "买入",
            "quantity": "200",
            "price": "10.05",
        },
        "capabilities": {"submit": False, "receipt_mapping": False},
    })
    adapter = FounderscQuantOpenCLIAdapter(
        opencli_command=("opencli",),
        profile="work",
        runner=runner,
    )
    plan = _plan()

    # The fake returns a prepare receipt for every command; probe remains a
    # pure capability read and does not infer submit support.
    capability = adapter.probe(plan)
    assert capability.environment == "mock"
    assert capability.supports_submit is False
    prepared = adapter.prepare(plan)
    assert prepared.status == BrokerStatus.PREPARED
    assert prepared.echoed == {
        "code": "000001.XSHE",
        "side": "BUY",
        "shares": 200,
        "limit_price": 10.05,
    }
    assert runner.commands[0][:4] == ["opencli", "--profile", "work", "foundersc-quant"]
    assert runner.commands[1][-2:] == ["-f", "json"]


def test_submit_is_a_no_route_guard_and_never_invokes_runner() -> None:
    runner = Runner({"status": "ready", "environment": "mock", "logical_account_id": "primary"})
    adapter = FounderscQuantOpenCLIAdapter(opencli_command=("opencli",), runner=runner)
    receipt = adapter.submit(_plan(), "claim-1")
    assert receipt.status == BrokerStatus.REJECTED
    assert receipt.reason == "NO_ROUTE_PROVEN"
    assert runner.commands == []


def test_reconcile_without_receipt_mapping_is_unknown_not_a_fill() -> None:
    runner = Runner({
        "status": "reconciled",
        "environment": "mock",
        "logical_account_id": "primary",
        "reconcile_complete": False,
        "reconcile_required": True,
        "capabilities": {"receipt_mapping": False},
    })
    adapter = FounderscQuantOpenCLIAdapter(opencli_command=("opencli",), runner=runner)
    receipt = adapter.reconcile(_plan(), {})
    assert receipt.status == BrokerStatus.UNKNOWN
    assert receipt.conclusive is False
    assert receipt.filled_shares == 0
    assert "BROKER_RECEIPT_MAPPING_UNPROVEN" in receipt.reason


def test_invalid_command_output_is_unknown_and_safe() -> None:
    class BadRunner:
        def __call__(self, command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, stdout="not-json\n", stderr="")

    adapter = FounderscQuantOpenCLIAdapter(opencli_command=("opencli",), runner=BadRunner())
    receipt = adapter.prepare(_plan())
    assert receipt.status == BrokerStatus.UNKNOWN
    assert receipt.conclusive is False
    assert receipt.error_code == "OPENCLI_INVALID_RECEIPT"
