from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import pytest

from xiaocao.live.foundersc_opencli import (
    FounderscQuantOpenCLIAdapter,
    OpenCLIAdapterError,
    release_foundersc_opencli_site_session,
    resolve_connected_opencli_profile,
)
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


def test_profile_resolution_selects_global_default_then_requires_edge() -> None:
    class ProfileRunner:
        def __call__(self, command, **_kwargs):
            if command[-2:] == ["profile", "list"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=(
                        "Connected Browser Bridge profiles\n\n"
                        "  du6r9r44 — connected v1.0.22\n"
                        "  9g3b5dck default — connected v1.0.22\n"
                    ),
                    stderr="",
                )
            profile = command[command.index("--profile") + 1]
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "Mozilla/5.0 Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
                    if profile == "du6r9r44"
                    else "Mozilla/5.0 Chrome/151.0.0.0 Safari/537.36"
                ),
                stderr="",
            )

    with pytest.raises(OpenCLIAdapterError, match="OPENCLI_EDGE_PROFILE_NOT_CONNECTED"):
        resolve_connected_opencli_profile(
            opencli_command=("opencli",),
            runner=ProfileRunner(),
            launch_edge=lambda: None,
            poll_attempts=1,
        )


def test_profile_resolution_fails_closed_when_only_chrome_is_connected() -> None:
    class ProfileRunner:
        def __call__(self, command, **_kwargs):
            if command[-2:] == ["profile", "list"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=(
                        "Connected Browser Bridge profiles\n\n"
                        "  9g3b5dck default — connected v1.0.22\n"
                    ),
                    stderr="",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="Mozilla/5.0 Chrome/151.0.0.0 Safari/537.36",
                stderr="",
            )

    with pytest.raises(OpenCLIAdapterError, match="OPENCLI_EDGE_PROFILE_NOT_CONNECTED"):
        resolve_connected_opencli_profile(
            opencli_command=("opencli",),
            runner=ProfileRunner(),
            launch_edge=lambda: None,
            poll_attempts=1,
        )


def test_multiple_edge_profiles_resolve_only_the_unique_default() -> None:
    class ProfileRunner:
        def __call__(self, command, **_kwargs):
            if command[-2:] == ["profile", "list"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=(
                        "Connected Browser Bridge profiles\n\n"
                        "  edge-one — connected v1.0.22\n"
                        "  edge-two default — connected v1.0.22\n"
                    ),
                    stderr="",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="Mozilla/5.0 Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
                stderr="",
            )

    assert resolve_connected_opencli_profile(
        opencli_command=("opencli",),
        runner=ProfileRunner(),
        launch_edge=lambda: None,
        poll_attempts=1,
    ) == "edge-two"
    with pytest.raises(OpenCLIAdapterError, match="OPENCLI_EDGE_PROFILE_MISMATCH"):
        resolve_connected_opencli_profile(
            "edge-one",
            opencli_command=("opencli",),
            runner=ProfileRunner(),
            launch_edge=lambda: None,
            poll_attempts=1,
        )


def test_explicit_profile_must_match_the_unique_connected_edge_profile() -> None:
    class ProfileRunner:
        def __call__(self, command, **_kwargs):
            if command[-2:] == ["profile", "list"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="  edge-only — connected v1.0.22\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="Mozilla/5.0 Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
                stderr="",
            )

    with pytest.raises(OpenCLIAdapterError, match="OPENCLI_EDGE_PROFILE_MISMATCH"):
        resolve_connected_opencli_profile(
            "some-other-profile",
            opencli_command=("opencli",),
            runner=ProfileRunner(),
            launch_edge=lambda: None,
            poll_attempts=1,
        )


def test_foundersc_startup_releases_only_its_stale_edge_site_lease() -> None:
    commands: list[list[str]] = []

    def runner(command, **_kwargs):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="released\n", stderr="")

    release_foundersc_opencli_site_session(
        "du6r9r44",
        opencli_command=("opencli",),
        runner=runner,
    )

    assert commands == [[
        "opencli",
        "--profile",
        "du6r9r44",
        "browser",
        "site:foundersc-quant",
        "close",
    ]]


def test_foundersc_startup_fails_closed_when_stale_lease_cannot_be_released() -> None:
    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="busy")

    with pytest.raises(OpenCLIAdapterError, match="OPENCLI_SITE_SESSION_RELEASE_FAILED"):
        release_foundersc_opencli_site_session(
            "du6r9r44",
            opencli_command=("opencli",),
            runner=runner,
        )


def test_probe_and_prepare_consume_only_template_receipt() -> None:
    runner = Runner({
        "status": "prepared_readback",
        "environment": "mock",
        "logical_account_id": "primary",
        "account_binding": "not_proven",
        "field_readback": {
            "strategy_name": "xiaocao-readback-2026-08-15-000001",
            "code": "000001",
            "side": "买入",
            "quantity": "200",
            "price": "10.05",
            "date": "2026-08-15",
            "hour": "9",
            "minute": "30",
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


def test_prepare_readonly_binds_page_account_to_keychain_proof() -> None:
    runner = Runner({
        "status": "unknown",
        "status_reason": "account_fingerprint_not_proven",
        "environment": "mock",
        "logical_account_id": "primary",
        "account_binding": "not_proven",
        "fund_account_fingerprint": "987******210",
        "requested_shares": 200,
        "order_price": 10.05,
        "submitted": False,
        "saved": False,
        "started": False,
        "ready_for_submit": False,
        "form_closed": True,
        "field_readback": {
            "strategy_name": "xiaocao-readback-2026-08-15-000001",
            "code": "000001",
            "side": "买入",
            "quantity": "200",
            "price": "10.05",
            "date": "2026-08-15",
            "hour": "9",
            "minute": "30",
        },
        "capabilities": {
            "submit": False,
            "form_readback": True,
            "account_binding": False,
        },
    })
    adapter = FounderscQuantOpenCLIAdapter(
        opencli_command=("opencli",),
        runner=runner,
        route="timed-order",
    )

    receipt = adapter.prepare_readonly(
        _plan(),
        expected_fund_account_fingerprint="987******210",
    )

    assert receipt.status == BrokerStatus.PREPARED
    assert receipt.account_binding == "proven"
    assert receipt.echoed == {
        "code": "000001.XSHE",
        "side": "BUY",
        "shares": 200,
        "limit_price": 10.05,
    }
    assert receipt.field_readback["submitted"] is False
    assert receipt.field_readback["saved"] is False
    assert receipt.field_readback["started"] is False
    assert receipt.field_readback["form_closed"] is True
    command = runner.commands[0]
    assert command[command.index("--date") + 1] == "2026-08-15"
    assert command[command.index("--time") + 1] == "09:30"
    assert command[command.index("--strategy-name") + 1] == (
        "xiaocao-readback-2026-08-15-000001"
    )


def test_prepare_readonly_fails_closed_on_page_keychain_account_mismatch() -> None:
    runner = Runner({
        "status": "unknown",
        "status_reason": "account_fingerprint_not_proven",
        "environment": "mock",
        "logical_account_id": "primary",
        "fund_account_fingerprint": "111******222",
        "submitted": False,
        "saved": False,
        "started": False,
        "ready_for_submit": False,
        "form_closed": True,
        "field_readback": {},
        "capabilities": {"submit": False, "form_readback": True},
    })
    adapter = FounderscQuantOpenCLIAdapter(
        opencli_command=("opencli",),
        runner=runner,
    )

    receipt = adapter.prepare_readonly(
        _plan(),
        expected_fund_account_fingerprint="987******210",
    )

    assert receipt.status == BrokerStatus.UNKNOWN
    assert receipt.error_code == "LIVE_PREPARE_READBACK_UNPROVEN"


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


def test_adapter_accepts_real_opencli_multiline_json_after_diagnostic() -> None:
    row = {
        "status": "environment_ready",
        "environment": "mock",
        "logical_account_id": "primary",
        "submitted": False,
        "saved": False,
        "started": False,
    }

    class PrettyRunner:
        def __call__(self, command, **_kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="connected to Browser Bridge\n" + json.dumps([row], indent=2),
                stderr="",
            )

    adapter = FounderscQuantOpenCLIAdapter(
        opencli_command=("opencli",),
        profile="profile-id",
        runner=PrettyRunner(),
    )

    receipt = adapter.ensure_environment(target="mock")

    assert receipt["status"] == "environment_ready"
    assert receipt["environment"] == "mock"


def test_adapter_rejects_multiple_top_level_json_receipts() -> None:
    row = {
        "status": "environment_ready",
        "environment": "mock",
        "logical_account_id": "primary",
        "submitted": False,
        "saved": False,
        "started": False,
    }

    class DuplicateRunner:
        def __call__(self, command, **_kwargs):
            document = json.dumps([row], ensure_ascii=False)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f"{document}\n{document}\n",
                stderr="",
            )

    adapter = FounderscQuantOpenCLIAdapter(
        opencli_command=("opencli",),
        runner=DuplicateRunner(),
    )

    with pytest.raises(OpenCLIAdapterError, match="OPENCLI_RECEIPT_CARDINALITY"):
        adapter.ensure_environment(target="mock")


def test_environment_preflight_switches_only_the_requested_environment() -> None:
    runner = Runner({
        "status": "environment_switched",
        "environment": "live",
        "expected_environment": "live",
        "logical_account_id": "primary",
        "account_binding": "not_proven",
        "submitted": False,
        "saved": False,
        "started": False,
        "field_readback": {
            "from_environment": "mock",
            "to_environment": "live",
            "changed": True,
        },
        "capabilities": {"submit": False, "environment_switch": True},
    })
    adapter = FounderscQuantOpenCLIAdapter(opencli_command=("opencli",), runner=runner)

    receipt = adapter.ensure_environment(
        target="live",
        expected_current="any",
        logical_account_id="primary",
    )

    assert receipt["status"] == "environment_switched"
    assert receipt["environment"] == "live"
    command = runner.commands[0]
    assert command[1:3] == ["foundersc-quant", "environment"]
    assert command[command.index("--target") + 1] == "live"
    assert command[command.index("--expected-current") + 1] == "any"
    assert command[-2:] == ["-f", "json"]


def test_live_allocation_facts_are_derived_from_complete_broker_asset_readback() -> None:
    runner = Runner({
        "status": "reconciled_partial",
        "environment": "live",
        "logical_account_id": "primary",
        "account_binding": "not_proven",
        "fund_account_fingerprint": "987******210",
        "observed_at": "2026-08-24T01:20:00.000Z",
        "reconcile_complete": False,
        "submitted": False,
        "saved": False,
        "started": False,
        "field_readback": {
            "assets": {
                "complete_scan": True,
                "allocation_summary": {
                    "complete": True,
                    "values": {
                        "总资产": "100,000.00",
                        "证券市值": "25,000.00",
                        "可用资金": "70,000.00",
                    },
                },
            }
        },
    })
    adapter = FounderscQuantOpenCLIAdapter(opencli_command=("opencli",), runner=runner)

    facts = adapter.read_live_allocation_facts(
        trade_date="2026-08-24",
        logical_account_id="primary",
        settled_nav=30_000,
        current_open_exposure=0,
        capital_basis_source="initial_book_b_capital",
        expected_fund_account_fingerprint="987******210",
        now=datetime(2026, 8, 24, 1, 21, tzinfo=timezone.utc),
    )

    assert facts["settled_nav"] == 30_000
    assert facts["available_cash"] == 70_000
    assert facts["current_open_exposure"] == 0
    assert facts["capital_basis_source"] == "initial_book_b_capital"
    assert facts["broker_total_assets"] == 100_000
    assert facts["broker_securities_market_value"] == 25_000
    assert facts["account_binding"] == "proven"
    assert len(facts["broker_receipt_sha256"]) == 64
    assert len(facts["allocation_capsule_sha256"]) == 64
    command = runner.commands[0]
    assert command[1:3] == ["foundersc-quant", "reconcile"]
    assert command[command.index("--scope") + 1] == "assets"
    assert command[command.index("--expected-environment") + 1] == "live"


def test_live_allocation_facts_reject_unproven_account_binding() -> None:
    runner = Runner({
        "status": "reconciled_partial",
        "environment": "live",
        "logical_account_id": "primary",
        "account_binding": "not_proven",
        "fund_account_fingerprint": "",
        "observed_at": "2026-08-24T01:20:00.000Z",
        "reconcile_complete": False,
        "field_readback": {},
    })
    adapter = FounderscQuantOpenCLIAdapter(opencli_command=("opencli",), runner=runner)

    with pytest.raises(OpenCLIAdapterError, match="LIVE_ALLOCATION_ACCOUNT_BINDING_UNPROVEN"):
        adapter.read_live_allocation_facts(
            trade_date="2026-08-24",
            logical_account_id="primary",
            settled_nav=30_000,
            current_open_exposure=0,
            capital_basis_source="initial_book_b_capital",
            expected_fund_account_fingerprint="987******210",
            now=datetime(2026, 8, 24, 1, 21, tzinfo=timezone.utc),
        )


def test_live_allocation_facts_reject_stale_broker_receipt() -> None:
    runner = Runner({
        "status": "reconciled_partial",
        "environment": "live",
        "logical_account_id": "primary",
        "account_binding": "not_proven",
        "fund_account_fingerprint": "987******210",
        "observed_at": "2026-08-24T01:00:00.000Z",
        "reconcile_complete": False,
        "field_readback": {
            "assets": {
                "complete_scan": True,
                "allocation_summary": {
                    "complete": True,
                    "values": {"总资产": "100000", "证券市值": "0", "可用资金": "30000"},
                },
            }
        },
    })
    adapter = FounderscQuantOpenCLIAdapter(opencli_command=("opencli",), runner=runner)

    with pytest.raises(OpenCLIAdapterError, match="LIVE_ALLOCATION_RECEIPT_STALE"):
        adapter.read_live_allocation_facts(
            trade_date="2026-08-24",
            logical_account_id="primary",
            settled_nav=30_000,
            current_open_exposure=0,
            capital_basis_source="initial_book_b_capital",
            expected_fund_account_fingerprint="987******210",
            now=datetime(2026, 8, 24, 1, 21, tzinfo=timezone.utc),
        )
