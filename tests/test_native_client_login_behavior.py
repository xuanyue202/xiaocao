"""Run the real first-login password-fill routine against AX fault scenarios."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.app_simulation


@pytest.fixture(scope="module")
def login_executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routine = source[source.index("private func fillClientLoginFromStandardInput("):source.index("// A stale login-success message")]
    harness = r'''
import Foundation
import CoreFoundation
private final class Element: NSObject { let name: String; init(_ name: String) { self.name = name } }
private typealias AXUIElement = Element
private enum AXError { case success, failure }
private let kAXValueAttribute = "value", kAXFocusedAttribute = "focus"
private let mode = CommandLine.arguments[1]
private let window = Element("window"), field = Element("password"), captcha = Element("captcha"), other = Element("other")
private var activated = false, value = "residual", secretReads = 0, secretWrites = 0, focusWrites = 0
private struct ActionResult: Codable {
 let attempted: Bool; let succeeded: Bool; let requiresUserInput: Bool
 let confirmPressed: Bool; let confirmationMode: String; let unlockPathProven: Bool
}
private struct Receipt: Codable {
 var status = "client_login_required", reason = "", surfaceState = "client_login_required"
 var tradeAccountFingerprint = "123******890", tradeAccountFingerprintCount = 1
 var appRunning = true, screenLocked = false, accessibilityTrusted = true
 var secureFieldClearedBeforeSet: Bool? = nil
 var action: ActionResult? = nil
}
private final class Running { let processIdentifier: pid_t; init(_ pid: pid_t) { processIdentifier = pid } }
private struct Observation {
 var receipt: Receipt
 let runningApplication: Running?
 let primaryWindow: Element?
 let secureFields: [Element]
 let clientLoginCaptchaFields: [Element]
}
private func CFEqual(_ a: Element, _ b: Element) -> Bool { a === b }
private func observe(command: String) -> Observation {
 var receipt = Receipt()
 if activated && mode == "account-changed" { receipt.tradeAccountFingerprint = "999******999" }
 if activated && mode == "screen-locked" { receipt.screenLocked = true }
 return Observation(receipt: receipt, runningApplication: Running(activated && mode == "pid-changed" ? 22 : 11),
    primaryWindow: activated && mode == "window-changed" ? other : window,
    secureFields: [activated && mode == "field-changed" ? other : field],
    clientLoginCaptchaFields: [activated && mode == "captcha-changed" ? other : captcha])
}
private func validFingerprint(_ value: String) -> Bool { value == "123******890" }
private func option(_ name: String, in args: [String]) -> String { "123******890" }
private func readStandardInputSecret() -> String? { secretReads += 1; return "fixture-secret" }
private func activateFounder(_ observation: Observation) -> Bool { activated = true; return true }
private func attribute(_ element: Element, _ name: String) -> AnyObject? {
 if mode == "clear-read-failed" { return nil }
 if mode == "clear-wrong-type" { return NSNumber(value: 0) }
 return value as NSString
}
private func stringAttribute(_ element: Element, _ name: String) -> String { attribute(element, name) as? String ?? "" }
private func AXUIElementSetAttributeValue(_ element: Element, _ name: CFString, _ content: CFTypeRef?) -> AXError {
 if name as String == kAXFocusedAttribute { focusWrites += 1; return mode == "focus-failed" ? .failure : .success }
 guard let text = content as? String else { return .failure }
 if text.isEmpty && mode == "clear-write-failed" { return .failure }
 if !text.isEmpty { secretWrites += 1; if mode == "set-failed" { return .failure } }
 value = text
 return .success
}
'''
    harness += routine
    harness += r'''
private let result = fillClientLoginFromStandardInput(arguments: ["--allow-stdin-secret"])
let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
print(String(data: try! encoder.encode(result), encoding: .utf8)!)
print("\(secretReads),\(secretWrites),\(focusWrites)")
'''
    directory = tmp_path_factory.mktemp("login-swift")
    path, executable = directory / "login.swift", directory / "login"
    path.write_text(harness)
    result = subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    return executable


def run_login(executable, mode):
    result = subprocess.run([str(executable), mode], capture_output=True, text=True, check=True, timeout=3)
    assert "fixture-secret" not in result.stdout + result.stderr
    receipt, counts = result.stdout.splitlines()
    return json.loads(receipt), counts.split(",")


def test_password_fill_requires_captcha_and_never_confirms_login(login_executable):
    receipt, counts = run_login(login_executable, "normal")
    assert receipt["status"] == "client_login_password_filled"
    assert counts == ["1", "1", "1"]
    assert receipt["action"]["confirm_pressed"] is False


@pytest.mark.parametrize("mode", ["clear-read-failed", "clear-wrong-type", "clear-write-failed"])
def test_missing_empty_readback_never_allows_secret_write(login_executable, mode):
    receipt, counts = run_login(login_executable, mode)
    assert receipt["status"] == "trade_password_clear_failed"
    assert counts[1:] == ["0", "0"]


@pytest.mark.parametrize("mode", ["account-changed", "pid-changed", "window-changed", "field-changed", "captcha-changed", "screen-locked"])
def test_activation_changed_login_target_never_receives_secret(login_executable, mode):
    receipt, counts = run_login(login_executable, mode)
    assert receipt["status"] == "client_login_surface_unproven"
    assert counts == ["0", "0", "0"]


@pytest.mark.parametrize("mode", ["set-failed", "focus-failed"])
def test_partial_fill_does_not_report_success(login_executable, mode):
    receipt, _ = run_login(login_executable, mode)
    assert receipt["status"] == "client_login_password_fill_failed"
    assert receipt["action"]["confirm_pressed"] is False
