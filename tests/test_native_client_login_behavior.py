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
    classifier = source[source.index("private func dismissLoginSuccessNotice("):source.index("private func checkDialogs(")]
    harness = r'''
import Foundation
import CoreFoundation
private struct Bounds { let x: Double; let y: Double; let width: Double; let height: Double }
private final class Element: NSObject {
 let name: String; let role: String; let title: String; let descriptionText: String; let identifier: String
 var children: [Element]; let area: Bounds
 init(_ name: String, role: String = "AXTextField", title: String = "", description: String = "", identifier: String = "", children: [Element] = [], area: Bounds = Bounds(x:20,y:20,width:200,height:100)) {
  self.name=name; self.role=role; self.title=title; self.descriptionText=description; self.identifier=identifier; self.children=children; self.area=area
 }
}
private typealias AXUIElement = Element
private enum AXError { case success, failure }
private let kAXValueAttribute="value", kAXFocusedAttribute="focus", kAXWindowsAttribute="windows", kAXChildrenAttribute="children"
private let kAXTitleAttribute="title", kAXDescriptionAttribute="description", kAXRoleAttribute="role", kAXSubroleAttribute="subrole", kAXIdentifierAttribute="identifier"
private let kAXCloseButtonAttribute="close", kAXMinimizeButtonAttribute="minimize", kAXZoomButtonAttribute="zoom", kAXPressAction="press"
private let kCGWindowOwnerPID="pid", kCGWindowBounds="bounds", kCGNullWindowID=0
private enum WindowOption { case optionOnScreenOnly }
private let mode = CommandLine.arguments[1]
private let window = Element("window",role:"AXWindow",area:Bounds(x:0,y:0,width:1000,height:800))
private let field=Element("password"), captcha=Element("captcha"), other=Element("other"), app=Element("app",role:"AXApplication")
private let button=Element("button",role:"AXButton",title:"确定",identifier:"action-button-1")
private var activated=false, value="residual", secretReads=0, secretWrites=0, focusWrites=0, presses=0
private struct ActionResult: Codable {
 let attempted: Bool; let succeeded: Bool; let requiresUserInput: Bool
 let confirmPressed: Bool; let confirmationMode: String; let unlockPathProven: Bool
}
private struct Receipt: Codable {
 let schemaVersion=2, helperVersion=14
 var status="client_login_required", reason="", surfaceState="client_login_required"
 var tradeAccountFingerprint="123******890", tradeAccountFingerprintCount=1
 var appRunning=true, screenLocked=false, accessibilityTrusted=true
 var secureFieldClearedBeforeSet: Bool?=nil, clientLoginNoticeDismissed: Bool?=nil
 var action: ActionResult?=nil
}
private final class Running { let processIdentifier: pid_t; init(_ pid: pid_t) { self.processIdentifier=pid } }
private struct Observation {
 var receipt: Receipt
 let runningApplication: Running?
 let primaryWindow: Element?
 let secureFields: [Element]
 let clientLoginCaptchaFields: [Element]
 let applicationElement: Element?=app
}
private func CFEqual(_ a: Element, _ b: Element) -> Bool { a === b }
private func observe(command: String) -> Observation {
 var receipt=Receipt()
 if activated && mode == "account-changed" || presses > 0 && mode == "notice-account-changed" { receipt.tradeAccountFingerprint="999******999" }
 if activated && mode == "screen-locked" { receipt.screenLocked=true }
 let changedAfterFill = secretWrites > 0
 return Observation(receipt:receipt, runningApplication:Running(activated && mode == "pid-changed" || changedAfterFill && mode == "late-pid-changed" ? 22:11),
    primaryWindow: activated && mode == "window-changed" || presses > 0 && mode == "notice-window-changed" ? other:window,
    secureFields:[activated && mode == "field-changed" || changedAfterFill && mode == "late-field-changed" ? other:field],
    clientLoginCaptchaFields:[activated && mode == "captcha-changed" ? other:captcha])
}
private func validFingerprint(_ value: String) -> Bool { value == "123******890" }
private func option(_ name: String, in args: [String]) -> String { "123******890" }
private func readStandardInputSecret() -> String? { secretReads += 1; return "fixture-secret" }
private func activateFounder(_ observation: Observation) -> Bool { activated=true; return true }
private func attribute(_ element: Element, _ name: String) -> AnyObject? {
 if element === app && name == kAXWindowsAttribute { return [window] as NSArray }
 if name == kAXChildrenAttribute { return element.children as NSArray }
 if element === field && name == kAXValueAttribute {
  if mode == "clear-read-failed" { return nil }
  if mode == "clear-wrong-type" { return NSNumber(value:0) }
  return value as NSString
 }
 return nil
}
private func stringAttribute(_ element: Element, _ key: String) -> String {
 switch key { case kAXRoleAttribute:return element.role; case kAXTitleAttribute:return element.title; case kAXDescriptionAttribute:return element.descriptionText; case kAXIdentifierAttribute:return element.identifier; default:return "" }
}
private func elementAttribute(_ element: Element, _ key: String) -> Element? { nil }
private func bounds(of element: Element) -> Bounds? { element.area }
private func maskedFingerprint(in text: String) -> String { "123******890" }
private func CGWindowListCopyWindowInfo(_ option: WindowOption, _ id: Int) -> AnyObject? {
 return [["pid":NSNumber(value:11),"bounds":["X":0,"Y":0,"Width":1000,"Height":800]]] as NSArray
}
private func makeSheet(_ text: String) -> Element {
 Element("sheet",role:"AXSheet",description:"alert",children:[Element("text",role:"AXStaticText",title:text),button])
}
private func AXUIElementPerformAction(_ element: Element, _ action: CFString) -> AXError {
 presses += 1
 if mode == "notice-press-failed" { return .failure }
 if mode != "notice-persistent" { window.children=[] }
 return .success
}
private func AXUIElementSetAttributeValue(_ element: Element, _ name: CFString, _ content: CFTypeRef?) -> AXError {
 if name as String == kAXFocusedAttribute { focusWrites += 1; return mode == "focus-failed" ? .failure:.success }
 guard let text=content as? String else { return .failure }
 if text.isEmpty && mode == "clear-write-failed" { return .failure }
 if !text.isEmpty {
  secretWrites += 1
  if mode == "set-failed" { return .failure }
  if mode == "set-silent-noop" { return .success }
  if mode == "late-dialog" { window.children=[makeSheet("未知错误")] }
 }
 value=text; return .success
}
if mode.hasPrefix("notice-") { window.children=[makeSheet("方正证券网上交易 请输入交易密码!")] }
if mode == "unknown-dialog" { window.children=[makeSheet("未知错误")] }
if mode == "credential-error" { window.children=[makeSheet("用户名或密码错误")] }
'''
    harness += classifier
    harness += routine
    harness += r'''
private let result = fillClientLoginFromStandardInput(arguments: ["--allow-stdin-secret"])
let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
print(String(data: try! encoder.encode(result), encoding: .utf8)!)
print("\(secretReads),\(secretWrites),\(focusWrites)")
print("\(presses),\(window.children.count)")
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
    receipt, counts, _ = result.stdout.splitlines()
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


def login_notice_result(executable, mode):
    result = subprocess.run([str(executable), mode], capture_output=True, text=True, check=True, timeout=4)
    assert "fixture-secret" not in result.stdout + result.stderr
    receipt, counts, notice_counts = result.stdout.splitlines()
    from xiaocao.live.foundersc_native_ax import _one_receipt
    parsed = _one_receipt(receipt.encode())
    return parsed, counts.split(","), notice_counts.split(",")


def test_real_empty_login_notice_dismissed_before_fill(login_executable):
    receipt, counts, notice_counts = login_notice_result(login_executable, "notice-normal")
    assert receipt["status"] == "client_login_password_filled"
    assert counts == ["1", "1", "1"]
    assert notice_counts == ["1", "0"]
    assert receipt["action"]["confirm_pressed"] is False


@pytest.mark.parametrize("mode", ["unknown-dialog", "credential-error", "notice-persistent", "notice-press-failed"])
def test_blocking_dialog_prevents_secret_read_and_success(login_executable, mode):
    receipt, counts, _ = login_notice_result(login_executable, mode)
    assert receipt["status"] == "client_login_notice_blocked"
    assert counts == ["0", "0", "0"]


@pytest.mark.parametrize("mode", ["notice-account-changed", "notice-window-changed"])
def test_notice_recovery_must_rebind_before_secret(login_executable, mode):
    receipt, counts, _ = login_notice_result(login_executable, mode)
    assert receipt["status"] == "client_login_surface_unproven"
    assert counts == ["0", "0", "0"]


@pytest.mark.parametrize("mode", ["late-dialog", "late-pid-changed", "late-field-changed"])
def test_fill_cannot_report_success_on_changed_or_blocked_surface(login_executable, mode):
    receipt, counts, notice_counts = login_notice_result(login_executable, mode)
    assert receipt["status"] == "client_login_password_fill_failed"
    assert counts == ["1", "1", "1"]
    assert notice_counts[0] == "0"
    assert receipt["action"]["confirm_pressed"] is False


def test_successful_ax_write_without_nonempty_readback_is_failure(login_executable):
    receipt, counts, _ = login_notice_result(login_executable, "set-silent-noop")
    assert receipt["status"] == "client_login_password_fill_failed"
    assert counts == ["1", "1", "1"]
    assert receipt["action"]["confirm_pressed"] is False
