"""Execute the production Swift unlock routine with deterministic AX faults.

No App or Keychain is opened. Fake secret text is never emitted by the harness.
"""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.app_simulation


@pytest.fixture(scope="module")
def unlock_executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required for unlock behavior verification")
    source = (Path(__file__).resolve().parents[1] /
        "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    types = source[source.index("private struct UnlockSnapshot:"):source.index("private struct Receipt:")]
    routine = source[source.index("private func secureFieldIsFocused("):source.index("\nlet arguments = Array(")]
    harness = r'''
import Foundation
import CoreFoundation
private struct Bounds: Codable { let x: Double; let y: Double; let width: Double; let height: Double }
private struct ActionResult: Codable {
    let attempted: Bool; let succeeded: Bool; let requiresUserInput: Bool
    let confirmPressed: Bool; let confirmationMode: String; let unlockPathProven: Bool
}
private final class Element: NSObject { let name: String; init(_ name: String) { self.name = name } }
private typealias AXUIElement = Element
private enum AXError { case success, failure }
private let kAXValueAttribute = "value"
private let kAXFocusedAttribute = "focus"
private let kAXFocusedUIElementAttribute = "focused-ui"
private let kAXPressAction = "press"
private let mode = CommandLine.arguments[1]
private let app = Element("app"), window = Element("window"), otherWindow = Element("other-window")
private let field = Element("secure"), otherField = Element("other-secure"), button = Element("button")
private var focused = otherField
private var elapsed = 0.0
private var secretReads = 0, valueWrites = 0, confirmations = 0, reads = 0
private var secureValue = "residual"
private var focusRequested = false
private var noticeDismissed = false
private func simulatedNow() -> Date { Date(timeIntervalSince1970: elapsed) }
private func wait(_ seconds: Double) { elapsed += seconds }
private func milliseconds(since: Date) -> Double { (elapsed - since.timeIntervalSince1970) * 1000 }
private final class Running {
    var isActive: Bool { mode == "busy" || mode == "semantic-busy" || (mode == "foreground-changed" && valueWrites > 0) }
    let processIdentifier: pid_t
    init(_ pid: pid_t = 11) { processIdentifier = pid }
}
private let running = Running()
private struct Receipt: Codable {
    let schemaVersion = 2, helperVersion = 14
    var status = "authentication_required", reason = "", surfaceState = "authentication_required"
    var tradeAccountFingerprint = "123******890", tradeAccountFingerprintCount = 1
    var secureFieldCount = 1, windowCount = 1
    var windowBounds: Bounds? = Bounds(x: 0, y: 0, width: 1000, height: 800)
    var appRunning = true, screenLocked = false, accessibilityTrusted = true, appActive = false
    var unlockFailureCategory: String? = nil
    var secureFieldClearedBeforeSet: Bool? = nil
    var loginNoticeDismissed: Bool? = nil
    var staleAuthErrorDismissed: Bool? = nil
    var action: ActionResult? = nil
    var unlockEvidence: UnlockEvidence? = nil
}
private struct Observation {
    var receipt: Receipt
    let runningApplication: Running?
    let applicationElement: Element?
    let primaryWindow: Element?
    let secureFields: [Element]
    let confirmButtons: [Element]
}
private func CFEqual(_ a: Element, _ b: Element) -> Bool { a === b }
private func elementAttribute(_ element: Element, _ key: String) -> Element? {
    if focusRequested && mode == "focus-delayed" && elapsed >= 0.25 { focused = field }
    return key == kAXFocusedUIElementAttribute ? focused : nil
}
private func attribute(_ element: Element, _ key: String) -> AnyObject? {
    if mode == "clear-read-failed" { return nil }
    return secureValue as NSString
}
private func AXUIElementSetAttributeValue(_ element: Element, _ key: CFString, _ value: CFTypeRef?) -> AXError {
    if key as String == kAXFocusedAttribute {
        focusRequested = true
        if !["focus-delayed", "focus-unproven"].contains(mode) { focused = field }
        return .success
    }
    if let text = value as? String {
        secureValue = text
        if !text.isEmpty { valueWrites += 1 }
    }
    return .success
}
private func AXUIElementPerformAction(_ element: Element, _ key: CFString) -> AXError {
    confirmations += 1
    return .success
}
private func postSingleReturnKey(to pid: pid_t) -> Bool { confirmations += 1; return true }
private func keyboardQuietForUnlock() -> Bool {
    return !["busy", "semantic-busy", "foreground-changed"].contains(mode)
}
private func bounds(of: Element) -> Bounds? { Bounds(x: 420, y: 300, width: 100, height: 20) }
private func guardedUnlockConfirmPoint(field: Bounds?, window: Bounds?) -> CGPoint? { CGPoint(x: 440, y: 350) }
private func guardedUnlockConfirmButton(window: Element?, point: CGPoint?) -> Element? { nil }
private func validFingerprint(_ text: String) -> Bool { text == "123******890" }
private func option(_ name: String, in arguments: [String]) -> String { "123******890" }
private func readStandardInputSecret() -> String? { secretReads += 1; return "fixture-secret" }
private func dismissLoginSuccessNotice(_ observation: Observation, expected: String,
                                      allowDismiss: Bool = true,
                                      allowStalePasswordError: Bool = false) -> (Bool, Bool, String) {
    if mode == "overlay" || (mode == "late-overlay" && valueWrites > 0) { return (false, false, "unknown-overlay") }
    if mode == "prior-error" { return (false, false, "unproved-error-sheet") }
    if mode.hasPrefix("stale-") && !noticeDismissed {
        guard allowStalePasswordError else { return (false, false, "stale-error-not-enabled") }
        noticeDismissed = true
        return (true, true, "known_notice_dismissed")
    }
    return (true, false, "clear")
}
private func observe(command: String) -> Observation {
    reads += 1
    var receipt = Receipt()
    receipt.appActive = running.isActive
    if mode == "prior-error" { receipt.unlockFailureCategory = "trade_password_incorrect" }
    if mode.hasPrefix("stale-") && (!noticeDismissed || mode == "stale-persistent") {
        receipt.unlockFailureCategory = "trade_password_incorrect"
    }
    if noticeDismissed && mode == "stale-account-changed" { receipt.tradeAccountFingerprint = "999******999" }
    if confirmations > 0 {
        if mode != "never-ready" && !(mode == "slow-ready" && elapsed < 1.2) {
            receipt.status = "query_only"; receipt.surfaceState = "query_only"; receipt.secureFieldCount = 0
        }
        if mode == "wrong-account" { receipt.tradeAccountFingerprint = "999******999" }
        if mode == "missing-account" { receipt.tradeAccountFingerprint = ""; receipt.tradeAccountFingerprintCount = 0 }
        if mode == "password-error" { receipt.unlockFailureCategory = "trade_password_incorrect" }
    }
    let changed = valueWrites > 0 && confirmations == 0
    return Observation(receipt: receipt, runningApplication: (mode == "restart" && confirmations > 0) || (noticeDismissed && mode == "stale-pid-changed") ? Running(22) : running, applicationElement: app,
        primaryWindow: (changed && mode == "window-changed") || (noticeDismissed && mode == "stale-window-changed") ? otherWindow : window,
        secureFields: receipt.secureFieldCount == 0 ? [] : [(changed && mode == "field-changed") || (noticeDismissed && mode == "stale-field-changed") ? otherField : field],
        confirmButtons: mode == "semantic-busy" ? [button] : [])
}
'''
    harness += types + routine.replace("DispatchTime.now()", "simulatedNow()").replace("started: DispatchTime", "started: Date").replace("Date()", "simulatedNow()").replace("Thread.sleep(forTimeInterval: ", "wait(")
    harness += r'''
private let receipt = unlockFromStandardInput(arguments: ["--allow-stdin-secret"])
let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
let payload = try! encoder.encode(receipt)
print(String(data: payload, encoding: .utf8)!)
print("\(secretReads),\(valueWrites),\(confirmations),\(reads),\(secureValue.isEmpty)")
'''
    directory = tmp_path_factory.mktemp("unlock-swift")
    path, executable = directory / "unlock.swift", directory / "unlock"
    path.write_text(harness)
    result = subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


def run_unlock(executable, mode):
    result = subprocess.run([str(executable), mode], capture_output=True, text=True, timeout=3, check=True)
    assert "fixture-secret" not in result.stdout + result.stderr
    receipt, counters = result.stdout.splitlines()
    from xiaocao.live.foundersc_native_ax import _one_receipt
    return _one_receipt(receipt), counters.split(",")


@pytest.mark.parametrize("mode", ["normal", "focus-delayed", "slow-ready"])
def test_unlock_waits_for_target_and_bound_readiness_without_reconfirmation(unlock_executable, mode):
    receipt, counters = run_unlock(unlock_executable, mode)
    assert receipt["status"] == "unlocked"
    assert counters[:3] == ["1", "1", "1"]
    assert receipt["unlock_evidence"]["stage"] == "ready"
    assert receipt["unlock_evidence"]["total_ms"] <= 3500


@pytest.mark.parametrize("mode", ["wrong-account", "missing-account", "restart", "never-ready", "password-error"])
def test_unlock_cannot_fabricate_success_or_repeat_confirmation(unlock_executable, mode):
    receipt, counters = run_unlock(unlock_executable, mode)
    assert receipt["status"] == "unlock_unproven"
    assert not receipt["action"]["succeeded"]
    assert counters[2] == "1"
    if mode == "wrong-account":
        assert receipt["trade_account_fingerprint"] == "999******999"
    assert receipt["unlock_evidence"]["total_ms"] <= 3200
    if mode == "password-error":
        assert receipt["unlock_evidence"]["readiness_polls"] == 1


@pytest.mark.parametrize("mode", ["focus-unproven", "overlay", "prior-error", "busy", "semantic-busy"])
def test_unlock_blocks_before_password_entry_when_target_or_keyboard_unproven(unlock_executable, mode):
    receipt, counters = run_unlock(unlock_executable, mode)
    assert counters[1:3] == ["0", "0"]
    assert receipt["action"]["attempted"] is False
    assert receipt["action"]["confirm_pressed"] is False
    assert receipt["unlock_evidence"]["total_ms"] <= 2500


@pytest.mark.parametrize("mode", ["window-changed", "field-changed", "foreground-changed", "late-overlay"])
def test_unlock_erases_field_and_never_confirms_changed_target(unlock_executable, mode):
    receipt, counters = run_unlock(unlock_executable, mode)
    assert receipt["status"] == "unlock_target_changed"
    assert counters[2] == "0" and counters[-1] == "true"
    assert receipt["action"]["attempted"] is True
    assert receipt["action"]["confirm_pressed"] is False


def test_unlock_failed_empty_read_is_not_proof_of_clearing(unlock_executable):
    receipt, counters = run_unlock(unlock_executable, "clear-read-failed")
    assert receipt["status"] == "trade_password_clear_failed"
    assert counters[1:3] == ["0", "0"]


def test_stale_alert_recovery_rebinds_before_one_password_attempt(unlock_executable):
    receipt, counters = run_unlock(unlock_executable, "stale-cleared")
    assert receipt["status"] == "unlocked"
    assert receipt["stale_auth_error_dismissed"] is True
    assert counters[:3] == ["1", "1", "1"]


@pytest.mark.parametrize("mode", ["stale-persistent", "stale-account-changed", "stale-pid-changed",
                                 "stale-window-changed", "stale-field-changed"])
def test_stale_alert_recovery_never_reads_secret_after_binding_changes(unlock_executable, mode):
    receipt, counters = run_unlock(unlock_executable, mode)
    assert receipt["status"] == "unlock_surface_unproven"
    assert counters[:3] == ["0", "0", "0"]
