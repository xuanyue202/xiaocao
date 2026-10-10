"""Execute production Swift date setting/readback against native AX faults."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.app_simulation


@pytest.fixture(scope="module")
def history_date_executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routine = source[source.index("private func observedHistoryDates("):source.index("private func emptyCapabilities(")]
    harness = r'''
import Foundation
import CoreFoundation
private struct Bounds { let x: Double; let y: Double; let width: Double; let height: Double }
private struct HistoryDateRange: Equatable { let start: String; let end: String }
private final class Element: NSObject {
 let role: String; let box: Bounds; var value: AnyObject; var children: [Element]
 init(_ role: String, _ x: Double, _ value: AnyObject = "2026/9/30" as NSString, children: [Element] = []) {
  self.role=role; self.box=Bounds(x:x,y:90,width:40,height:20); self.value=value; self.children=children
 }
}
private typealias AXUIElement = Element
private enum AXError { case success, failure }
private let kAXRoleAttribute="role", kAXChildrenAttribute="children", kAXValueAttribute="value"
private let maximumDepth=20, maximumNodes=100
private let mode=CommandLine.arguments[1]
private var writes=0, observations=0
private let left=Element("AXDateTimeArea",100), right=Element("AXDateTimeArea",200)
private let window=Element("AXWindow",0,children:[left,right]), otherWindow=Element("AXWindow",0,children:[left,right])
private let windowBox=Bounds(x:0,y:0,width:1000,height:1000)
private struct Receipt { let windowBounds: Bounds?; let tradeAccountFingerprint: String; let tradeAccountFingerprintCount: Int }
private final class Running { let processIdentifier: Int; init(_ pid: Int) { processIdentifier=pid } }
private struct Observation { let primaryWindow: Element?; let receipt: Receipt; let runningApplication: Running? }
private func snapshot(_ changed: Bool=false) -> Observation {
 return Observation(primaryWindow:changed && mode == "window-change" ? otherWindow:window,
  receipt:Receipt(windowBounds:windowBox,tradeAccountFingerprint:changed && mode == "account-change" ? "other":"bound",
                  tradeAccountFingerprintCount:changed && mode == "duplicate-account" ? 2:1),
  runningApplication:Running(changed && mode == "pid-change" ? 22:11))
}
private func observe(command: String) -> Observation { observations += 1; return snapshot(observations >= 2) }
private func attribute(_ element: Element, _ key: String) -> AnyObject? {
 if key == kAXChildrenAttribute { return element.children as NSArray }
 if key == kAXValueAttribute { return element.value }
 return nil
}
private func stringAttribute(_ element: Element, _ key: String) -> String { key == kAXRoleAttribute ? element.role:"" }
private func bounds(of element: Element) -> Bounds? { element.box }
private func isSettable(_ element: Element, _ key: String) -> Bool { mode != "not-settable" }
private func CFEqual(_ a: Element, _ b: Element) -> Bool { a === b }
private func AXUIElementSetAttributeValue(_ element: Element, _ key: CFString, _ value: CFTypeRef) -> AXError {
 writes += 1
 if mode == "first-fails" || mode == "second-fails" && writes == 2 { return .failure }
 if mode != "noop" { element.value=value }
 return .success
}
'''
    harness += routine
    harness += r'''
if mode == "date-value" {
 let formatter=DateFormatter(); formatter.dateFormat="yyyy-MM-dd"; formatter.timeZone=TimeZone(identifier:"Asia/Shanghai")
 left.value=formatter.date(from:"2026-09-30")! as NSDate; right.value=left.value
}
if mode == "bad-value" { right.value=NSNumber(value:3) }
if mode == "extra-control" { window.children.append(Element("AXDateTimeArea",280)) }
let target=mode == "bad-target" ? "2026-02-30":"2026-10-09"
let result=setHistoryDates(snapshot(),target:target,fingerprint:"bound")
print(String(data:try! JSONSerialization.data(withJSONObject:["success":result,"writes":writes]),encoding:.utf8)!)
'''
    folder = tmp_path_factory.mktemp("history-date-swift")
    path, executable = folder / "dates.swift", folder / "dates"
    path.write_text(harness)
    build = subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, text=True, timeout=45)
    assert build.returncode == 0, build.stderr
    return executable


@pytest.mark.parametrize("mode", ["normal", "date-value"])
def test_production_sets_both_string_and_date_controls(history_date_executable, mode):
    result = subprocess.run([str(history_date_executable), mode], capture_output=True, text=True, check=True, timeout=3)
    assert json.loads(result.stdout) == {"success": True, "writes": 2}


@pytest.mark.parametrize("mode,writes", [("not-settable", 0), ("bad-value", 0), ("extra-control", 0),
    ("bad-target", 0), ("first-fails", 1), ("second-fails", 2), ("noop", 2),
    ("window-change", 1), ("account-change", 1), ("duplicate-account", 1), ("pid-change", 1)])
def test_production_date_failure_never_reports_scope_success(history_date_executable, mode, writes):
    result = subprocess.run([str(history_date_executable), mode], capture_output=True, text=True, check=True, timeout=3)
    assert json.loads(result.stdout) == {"success": False, "writes": writes}
