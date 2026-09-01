from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from xiaocao.live.foundersc_keychain import SECURITY_COMMAND, TRADE_SERVICE
from xiaocao.live.foundersc_native_ax import (
    SCHEMA_VERSION,
    FounderscNativeAXClient,
    FounderscNativeAXError,
    expected_helper_path,
    native_runtime_ready,
    remote_bootstrap_guidance,
    source_digest,
)


def _receipt(**overrides) -> bytes:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "helper_version": 1,
        "command": "probe",
        "status": "authentication_required",
        "surface_state": "authentication_required",
        "accessibility_trusted": True,
        "app_running": True,
        "capabilities": {
            "probe": True,
            "focus_unlock": True,
            "keychain_unlock_candidate": True,
            "focus_client_login_captcha": False,
            "keychain_client_login_fill_candidate": False,
            "prepare": False,
            "submit": False,
            "read_position_values": False,
            "unattended_recovery_proven": False,
        },
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def _helper(tmp_path: Path) -> Path:
    path = tmp_path / "foundersc-native-ax"
    path.write_bytes(b"test helper")
    path.chmod(0o755)
    return path


class HelperRunner:
    def __init__(self, stdout: bytes):
        self.stdout = stdout
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), dict(kwargs)))
        return subprocess.CompletedProcess(command, 0, stdout=self.stdout, stderr=b"")


def test_probe_parses_one_sanitized_versioned_receipt(tmp_path: Path) -> None:
    runner = HelperRunner(_receipt())
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    receipt = client.probe(table_audit=True)

    assert receipt.status == "authentication_required"
    assert receipt.trade_ready is False
    assert runner.calls[0][0][1:] == ["probe", "--table-audit"]
    assert runner.calls[0][1]["input"] is None


def test_receipt_with_sensitive_key_is_rejected(tmp_path: Path) -> None:
    runner = HelperRunner(_receipt(password="must-never-cross-seam"))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(
        FounderscNativeAXError,
        match="NATIVE_AX_RECEIPT_CONTAINS_SENSITIVE_KEY",
    ):
        client.probe()


def test_schema_mismatch_fails_closed(tmp_path: Path) -> None:
    runner = HelperRunner(_receipt(schema_version=999))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(FounderscNativeAXError, match="NATIVE_AX_SCHEMA_MISMATCH"):
        client.probe()


class KeychainAndHelperRunner:
    def __init__(self):
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        argv = list(command)
        self.calls.append((argv, dict(kwargs)))
        if argv[0] == SECURITY_COMMAND:
            assert argv[-1] == TRADE_SERVICE
            if "-w" in argv:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=b"test-secret\n",
                    stderr=b"",
                )
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=b'    "acct"<blob>="1234567890"\n',
                stderr=b"",
            )
        is_login_fill = argv[1] == "fill-client-login-stdin"
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=_receipt(
                command=argv[1],
                status=(
                    "client_login_password_filled" if is_login_fill else "unlocked"
                ),
                surface_state=(
                    "client_login_required" if is_login_fill else "trade_ready"
                ),
                trade_account_fingerprint="123******890",
                action={
                    "attempted": True,
                    "succeeded": True,
                    "requires_user_input": False,
                    "confirm_pressed": True,
                    "unlock_path_proven": True,
                },
            ),
            stderr=b"",
        )


def test_keychain_unlock_uses_stdin_and_only_masked_account_in_argv(
    tmp_path: Path,
) -> None:
    runner = KeychainAndHelperRunner()
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    receipt = client.unlock_from_keychain(
        explicitly_enabled=True,
        keychain_runner=runner,
    )

    assert receipt.status == "unlocked"
    helper_argv, helper_kwargs = runner.calls[-1]
    assert helper_argv[1:] == [
        "unlock-stdin",
        "--allow-stdin-secret",
        "--expected-fingerprint",
        "123******890",
    ]
    assert helper_kwargs["input"] == b"test-secret"
    assert "test-secret" not in " ".join(helper_argv)
    assert "1234567890" not in " ".join(helper_argv)
    assert "test-secret" not in repr(receipt.as_dict())
    assert "1234567890" not in repr(receipt.as_dict())


def test_keychain_unlock_requires_explicit_enablement(tmp_path: Path) -> None:
    runner = KeychainAndHelperRunner()
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(
        FounderscNativeAXError,
        match="NATIVE_AX_KEYCHAIN_UNLOCK_NOT_EXPLICITLY_ENABLED",
    ):
        client.unlock_from_keychain(keychain_runner=runner)

    assert runner.calls == []


def test_client_login_fill_uses_stdin_and_never_requests_login_press(
    tmp_path: Path,
) -> None:
    runner = KeychainAndHelperRunner()
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    receipt = client.fill_client_login_from_keychain(
        explicitly_enabled=True,
        keychain_runner=runner,
    )

    assert receipt.status == "client_login_password_filled"
    helper_argv, helper_kwargs = runner.calls[-1]
    assert helper_argv[1:] == [
        "fill-client-login-stdin",
        "--allow-stdin-secret",
        "--expected-fingerprint",
        "123******890",
    ]
    assert helper_kwargs["input"] == b"test-secret"
    assert "test-secret" not in " ".join(helper_argv)


def test_native_prepare_transports_bounded_order_fields_without_submit(
    tmp_path: Path,
) -> None:
    runner = HelperRunner(_receipt(
        status="prepared",
        surface_state="trade_ready",
        order_readback={
            "code": "000001",
            "side": "buy",
            "price": "10",
            "quantity": 100,
            "field_mapping_proven": True,
            "submit_control_count": 1,
            "submitted": False,
            "saved": False,
            "started": False,
            "form_cleared": True,
        },
    ))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    receipt = client.prepare_order(
        code="000001.XSHE",
        side="BUY",
        price=10.0,
        quantity=100,
        expected_fingerprint="123******890",
        clear_after_readback=True,
    )

    assert receipt.status == "prepared"
    argv, kwargs = runner.calls[-1]
    assert argv[1:] == [
        "prepare-order",
        "--allow-order-prepare",
        "--code",
        "000001",
        "--side",
        "buy",
        "--price",
        "10",
        "--quantity",
        "100",
        "--expected-fingerprint",
        "123******890",
        "--clear-after-readback",
    ]
    assert kwargs["input"] is None


def test_native_submit_requires_explicit_enablement_and_one_helper_call(
    tmp_path: Path,
) -> None:
    runner = HelperRunner(_receipt(
        status="submit_confirmed",
        surface_state="trade_ready",
    ))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(
        FounderscNativeAXError,
        match="NATIVE_AX_SINGLE_SUBMIT_NOT_EXPLICITLY_ENABLED",
    ):
        client.submit_prepared_order(
            code="000001.XSHE",
            side="BUY",
            price=10.0,
            quantity=100,
            expected_fingerprint="123******890",
        )
    assert runner.calls == []

    receipt = client.submit_prepared_order(
        code="000001.XSHE",
        side="BUY",
        price=10.0,
        quantity=100,
        expected_fingerprint="123******890",
        explicitly_enabled=True,
    )
    assert receipt.status == "submit_confirmed"
    argv, _kwargs = runner.calls[-1]
    assert argv[1] == "submit-prepared-order"
    assert argv.count("--allow-single-submit") == 1


def test_pending_order_confirmation_probe_and_single_confirm_are_separate(
    tmp_path: Path,
) -> None:
    runner = HelperRunner(_receipt(
        helper_version=7,
        status="order_confirmation_ready",
        surface_state="trade_ready",
    ))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    probe = client.probe_pending_order_confirmation(
        code="512010.XSHG",
        side="BUY",
        price=0.35,
        quantity=100,
        expected_fingerprint="123******890",
    )
    assert probe.status == "order_confirmation_ready"
    assert runner.calls[-1][0][1:] == [
        "probe-pending-order-confirmation",
        "--code",
        "512010",
        "--side",
        "buy",
        "--price",
        "0.35",
        "--quantity",
        "100",
        "--expected-fingerprint",
        "123******890",
    ]

    with pytest.raises(
        FounderscNativeAXError,
        match="NATIVE_AX_SINGLE_ORDER_CONFIRMATION_NOT_EXPLICITLY_ENABLED",
    ):
        client.confirm_pending_order(
            code="512010.XSHG",
            side="BUY",
            price=0.35,
            quantity=100,
            expected_fingerprint="123******890",
        )
    assert len(runner.calls) == 1

    runner.stdout = _receipt(
        helper_version=7,
        status="submit_confirmed",
        surface_state="trade_ready",
    )
    confirmed = client.confirm_pending_order(
        code="512010.XSHG",
        side="BUY",
        price=0.35,
        quantity=100,
        expected_fingerprint="123******890",
        explicitly_enabled=True,
    )
    assert confirmed.status == "submit_confirmed"
    argv, _kwargs = runner.calls[-1]
    assert argv[1] == "confirm-pending-order"
    assert argv.count("--allow-single-order-confirmation") == 1
    assert "--allow-single-submit" not in argv


def test_native_cancel_requires_explicit_enablement_and_exact_order_id(
    tmp_path: Path,
) -> None:
    runner = HelperRunner(_receipt(
        helper_version=6,
        status="cancel_confirmed",
        surface_state="query_only",
    ))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(
        FounderscNativeAXError,
        match="NATIVE_AX_SINGLE_CANCEL_NOT_EXPLICITLY_ENABLED",
    ):
        client.cancel_order(
            order_id="6000003",
            code="515120.XSHG",
            side="BUY",
            price=0.6,
            quantity=100,
            expected_fingerprint="123******890",
        )
    assert runner.calls == []

    receipt = client.cancel_order(
        order_id="6000003",
        code="515120.XSHG",
        side="BUY",
        price=0.6,
        quantity=100,
        expected_fingerprint="123******890",
        explicitly_enabled=True,
    )
    assert receipt.status == "cancel_confirmed"
    argv, _kwargs = runner.calls[-1]
    assert argv[1:] == [
        "cancel-order",
        "--allow-single-cancel",
        "--order-id",
        "6000003",
        "--code",
        "515120",
        "--side",
        "buy",
        "--price",
        "0.6",
        "--quantity",
        "100",
        "--expected-fingerprint",
        "123******890",
    ]


def test_native_cancel_selection_probe_never_uses_cancel_flag(tmp_path: Path) -> None:
    runner = HelperRunner(_receipt(
        helper_version=6,
        status="cancel_selection_proven",
        surface_state="query_only",
    ))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    client.probe_cancel_selection(
        order_id="6000002",
        code="515120.XSHG",
        side="BUY",
        price=0.646,
        quantity=100,
        expected_fingerprint="123******890",
        explicitly_enabled=True,
    )

    argv, _kwargs = runner.calls[-1]
    assert argv[1] == "probe-cancel-selection"
    assert argv.count("--allow-cancel-selection-probe") == 1
    assert "--allow-single-cancel" not in argv


def test_expected_helper_path_is_bound_to_source_digest() -> None:
    root = Path(__file__).resolve().parents[1]

    digest = source_digest(root)
    path = expected_helper_path(root)

    assert len(digest) == 64
    assert path.parts[-2:] == (digest, "foundersc-native-ax")


def test_swift_read_query_supports_historical_order_and_trade_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "native"
        / "foundersc_ax_executor"
        / "Sources"
        / "FounderscNativeAX"
        / "main.swift"
    ).read_text(encoding="utf-8")

    assert '"history-orders": "历史委托"' in source
    assert '"history-trades": "历史成交"' in source
    assert 'case "history-orders": expectedX = 0.428' in source
    assert 'case "history-trades": expectedX = 0.515' in source
    assert 'case "funds": expectedX = surfaceState == "query_only" ? 0.863' in source
    assert 'return (pointForSubstring(label, in: candidates[0]), 1)' in source
    assert 'case "today-orders", "history-orders":' in source
    assert 'case "today-trades", "history-trades":' in source


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, True),
        (
            {
                "status": "client_login_required",
                "surface_state": "client_login_required",
            },
            True,
        ),
        ({"screen_locked": True, "status": "screen_locked"}, False),
        ({"surface_state": "incomplete"}, False),
        ({"accessibility_trusted": False}, False),
        ({"app_running": False}, False),
    ],
)
def test_native_runtime_ready_is_fail_closed(overrides, expected) -> None:
    payload = json.loads(_receipt(**overrides))

    assert native_runtime_ready(payload) is expected


@pytest.mark.parametrize(
    ("native_overrides", "keychain", "expected_status", "expected_action"),
    [
        (
            {"status": "trade_ready", "surface_state": "trade_ready"},
            {},
            "ready",
            "none",
        ),
        (
            {
                "status": "client_login_required",
                "surface_state": "client_login_required",
            },
            {"trade_item_present": True, "trade_account_present": True},
            "action_required",
            "fill_login_password_then_solve_captcha",
        ),
        (
            {},
            {"trade_item_present": True, "trade_account_present": True},
            "action_required",
            "unlock_trade_once",
        ),
        (
            {},
            {},
            "action_required",
            "configure_trade_keychain",
        ),
        (
            {"screen_locked": True, "status": "screen_locked"},
            {},
            "blocked",
            "unlock_macos",
        ),
        (
            {
                "status": "app_absent",
                "surface_state": "app_absent",
                "app_running": False,
            },
            {},
            "action_required",
            "launch_foundersc",
        ),
        (
            {
                "status": "accessibility_denied",
                "surface_state": "accessibility_denied",
                "accessibility_trusted": False,
            },
            {},
            "blocked",
            "grant_accessibility_to_codex_or_terminal",
        ),
        (
            {"status": "query_only", "surface_state": "query_only"},
            {},
            "limited",
            "open_ordinary_trade_surface_then_reprobe",
        ),
    ],
)
def test_remote_bootstrap_guidance_is_bounded_state_machine(
    native_overrides,
    keychain,
    expected_status,
    expected_action,
) -> None:
    native = json.loads(_receipt(**native_overrides))

    guidance = remote_bootstrap_guidance(native, keychain)

    assert guidance["status"] == expected_status
    assert guidance["next_action"] == expected_action
    assert guidance["order_prepare_authorized"] is False
    assert guidance["order_submit_authorized"] is False
    rendered = json.dumps(guidance)
    assert "test-secret" not in rendered
    assert "1234567890" not in rendered


def test_swift_submit_confirmation_fallback_is_exact_and_single_point() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "native"
        / "foundersc_ax_executor"
        / "Sources"
        / "FounderscNativeAX"
        / "main.swift"
    ).read_text(encoding="utf-8")

    assert "confirmationCandidate,\n       confirmationMarker,\n       confirmationOrderMatched" in source
    assert "guardedOCRConfirmationPoint" not in source
    assert "ocr_guarded_order_confirmation" not in source
    assert 'quantity_field_single_return' in source
    assert 'secure_field_single_return' in source
    assert 'semantic_focused_dialog_button' in source
    assert 'postSingleReturnKey()' in source
    assert 'rendered.contains("交易确认")' in source
    assert 'case "probe-pending-order-confirmation"' in source
    assert 'case "confirm-pending-order"' in source
    assert 'arguments.contains("--allow-single-order-confirmation")' in source
    assert 'tableShapes[0].auditComplete' in source
    assert 'minimumCriticalOCRConfidence: Float = 0.50' in source
    assert 'criticalConfidenceProven' in source
    assert 'focusedCancelDialogControls(postClick)' in source
    assert 'ocr_guarded_cancel_confirmation' not in source
    assert 'func editDistance' not in source
    assert 'submit_result_acknowledged' in source
    assert 'cancel_result_acknowledged' in source
    assert '委托已提交' in source
    assert '撤单已提交' in source
    assert source.count('postSingleReturnKey()') == 3


def test_swift_observation_ignores_focused_accessory_windows() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "native"
        / "foundersc_ax_executor"
        / "Sources"
        / "FounderscNativeAX"
        / "main.swift"
    ).read_text(encoding="utf-8")

    assert "let largestWindow = windows.max" in source
    assert "let roots: [AXUIElement] = primaryWindow.map { [$0] } ?? []" in source
    assert "roots = windows" not in source
    assert '== "通达信键盘精灵"' in source
    assert "kAXCloseButtonAttribute" in source
    assert "guard dismissKnownFounderAccessoryWindow(running) else" in source
    assert "normalizeFounderWindowForAction" in source
    assert 'if command != "probe"' in source


def test_swift_bounded_cancel_side_covers_exact_text_at_low_confidence() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "native"
        / "foundersc_ax_executor"
        / "Sources"
        / "FounderscNativeAX"
        / "main.swift"
    ).read_text(encoding="utf-8")
    start = source.index("let exactTargetIndices")
    end = source.index("let boundedSideFallbackProven", start)
    selection = source[start:end]

    assert "if !query.parsingProven," in selection
    assert "targetIndices.isEmpty" not in selection
    assert 'Set(query.lowConfidenceCriticalHeaders) == Set(["买卖标志"])' in selection
    assert 'selectionProofMode = "exact_numeric_tuple_bounded_side_suffix"' in selection
