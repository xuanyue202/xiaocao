"""Execute the production stale-sheet classifier and dismissal against AX faults."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.app_simulation


@pytest.fixture(scope="module")
def alert_executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routine = source[source.index("private func dismissLoginSuccessNotice("):source.index("private func checkDialogs(")]
    harness = r'''
import Foundation
import CoreFoundation
private struct Bounds { let x: Double; let y: Double; let width: Double; let height: Double }
private final class Element: NSObject {
 let role: String; let title: String; let descriptionText: String; let identifier: String
 var children: [Element]; let area: Bounds
 init(_ role: String, _ title: String = "", _ descriptionText: String = "", _ identifier: String = "", children: [Element] = [], area: Bounds = Bounds(x: 20,y:20,width:200,height:100)) {
  self.role=role; self.title=title; self.descriptionText=descriptionText; self.identifier=identifier; self.children=children; self.area=area
 }
}
private typealias AXUIElement = Element
private enum AXError { case success, failure }
private let kAXWindowsAttribute="windows", kAXChildrenAttribute="children", kAXTitleAttribute="title", kAXValueAttribute="value"
private let kAXDescriptionAttribute="description", kAXRoleAttribute="role", kAXSubroleAttribute="subrole", kAXIdentifierAttribute="identifier"
private let kAXCloseButtonAttribute="close", kAXMinimizeButtonAttribute="minimize", kAXZoomButtonAttribute="zoom", kAXPressAction="press"
private let kCGWindowOwnerPID="pid", kCGWindowBounds="bounds", kCGNullWindowID=0
private enum WindowOption { case optionOnScreenOnly }
private let mode=CommandLine.arguments[1]
private var presses=0, dismissed=false
private let button=Element("AXButton","确定","",mode == "wrong-button" ? "unknown-button" : "action-button-1")
private let noticeText = mode.hasPrefix("client-") && mode != "client-credential-error" ? "方正证券网上交易 请输入交易密码!" : "用户名或密码错误"
private let text=Element("AXStaticText",mode.hasSuffix("success-message") ? "1234567890 测试的交易已重新登录成功!" : (mode == "mixed-text" || mode == "client-mixed-text" ? noticeText + " 交易委托确认" : noticeText))
private let sheet=Element(mode == "wrong-role" ? "AXWindow" : "AXSheet", mode.hasSuffix("success-message") ? "消息中心" : "", mode == "wrong-description" ? "unknown" : "alert", children:[text,button], area:Bounds(x:mode == "outside" ? 1500:20,y:20,width:200,height:100))
private let primary=Element("AXWindow", children:[sheet], area:Bounds(x:0,y:0,width:1000,height:800))
private let app=Element("AXApplication")
private final class Running { let processIdentifier: pid_t=11 }
private struct Observation { let applicationElement: Element?; let runningApplication: Running?; let primaryWindow: Element? }
private func attribute(_ element: Element, _ key: String) -> AnyObject? {
 if element === app && key == kAXWindowsAttribute { return (mode == "wrong-role" ? [primary,sheet] : [primary]) as NSArray }
 if key == kAXChildrenAttribute { return element.children as NSArray }
 return nil
}
private func stringAttribute(_ element: Element, _ key: String) -> String {
 switch key { case kAXRoleAttribute:return element.role; case kAXTitleAttribute:return element.title; case kAXDescriptionAttribute:return element.descriptionText; case kAXIdentifierAttribute:return element.identifier; default:return "" }
}
private func elementAttribute(_ element: Element, _ key: String) -> Element? { mode.hasSuffix("success-message") && element === sheet && key == kAXCloseButtonAttribute ? button:nil }
private func bounds(of element: Element) -> Bounds? { element.area }
private func CFEqual(_ a: Element, _ b: Element) -> Bool { a === b }
private func maskedFingerprint(in text: String) -> String { "123******890" }
private func CGWindowListCopyWindowInfo(_ option: WindowOption, _ id: Int) -> AnyObject? {
 if mode == "invisible" { return [] as NSArray }
 return [["pid":NSNumber(value:11),"bounds":["X":0,"Y":0,"Width":1000,"Height":800]]] as NSArray
}
private func AXUIElementPerformAction(_ element: Element, _ action: CFString) -> AXError {
 presses += 1
 if mode == "press-failed" { return .failure }
 if mode != "persistent" { primary.children=[]; dismissed=true }
 return .success
}
'''
    harness += routine
    harness += r'''
if mode == "extra-control" { sheet.children.append(Element("AXTextField")) }
if mode == "extra-button" || mode == "client-extra-button" { sheet.children.append(Element("AXButton","取消")) }
if mode == "duplicate" { primary.children.append(Element("AXSheet","","alert",children:[text,button])) }
let result=dismissLoginSuccessNotice(Observation(applicationElement:app,runningApplication:Running(),primaryWindow:primary), expected:"123******890",allowStalePasswordError:mode != "not-enabled" && !mode.hasPrefix("client-"),allowClientPasswordRequiredNotice:mode.hasPrefix("client-") && mode != "client-not-enabled",allowLoginSuccessNotice:!mode.hasPrefix("client-"))
print(String(data:try! JSONSerialization.data(withJSONObject:["clear":result.0,"dismissed":result.1,"presses":presses]),encoding:.utf8)!)
'''
    directory = tmp_path_factory.mktemp("alert-swift")
    path, executable = directory / "alert.swift", directory / "alert"
    path.write_text(harness)
    result = subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    return executable


def run_alert(executable, mode):
    result = subprocess.run([str(executable), mode], capture_output=True, text=True, check=True, timeout=3)
    return json.loads(result.stdout)


def test_exact_stale_alert_dismissed_once_and_proven_gone(alert_executable):
    assert run_alert(alert_executable, "normal") == {"clear": True, "dismissed": True, "presses": 1}


@pytest.mark.parametrize("mode", ["wrong-role", "wrong-description", "wrong-button", "mixed-text", "outside",
                                 "invisible", "extra-control", "extra-button", "duplicate", "not-enabled",
                                 "client-not-enabled", "client-credential-error", "client-mixed-text", "client-extra-button", "client-success-message"])
def test_unknown_or_ambiguous_sheet_never_pressed(alert_executable, mode):
    assert run_alert(alert_executable, mode) == {"clear": False, "dismissed": False, "presses": 0}


@pytest.mark.parametrize("mode", ["press-failed", "persistent"])
def test_press_without_disappearance_is_not_recovery(alert_executable, mode):
    assert run_alert(alert_executable, mode) == {"clear": False, "dismissed": False, "presses": 1}


def test_client_empty_password_validation_notice_has_separate_authority(alert_executable):
    assert run_alert(alert_executable, "client-required") == {"clear": True, "dismissed": True, "presses": 1}


def test_in_session_known_success_message_authority_preserved(alert_executable):
    assert run_alert(alert_executable, "session-success-message") == {"clear": True, "dismissed": True, "presses": 1}
