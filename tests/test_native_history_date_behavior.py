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
import CoreGraphics
private struct Bounds { let x: Double; let y: Double; let width: Double; let height: Double }
private struct HistoryDateRange: Equatable { let start: String; let end: String }
private final class Element: NSObject {
 let role: String; let subrole: String; let box: Bounds; var value: AnyObject; var children: [Element]
 init(_ role: String, _ x: Double, _ value: AnyObject = "2026/9/30" as NSString, children: [Element] = [],
      subrole: String="", y: Double=90, width: Double=80, height: Double=20) {
  self.role=role; self.subrole=subrole; self.box=Bounds(x:x,y:y,width:width,height:height); self.value=value; self.children=children
 }
}
private typealias AXUIElement = Element
private enum AXError { case success, failure }
private let kAXRoleAttribute="role", kAXChildrenAttribute="children", kAXValueAttribute="value"
private let kAXSubroleAttribute="subrole"
private let maximumDepth=20, maximumNodes=100
private let mode=CommandLine.arguments[1]
private var writes=0, observations=0, actionCount=0
private var pendingAction: (() -> Void)?
private var arrowChanged=false
private var selectedComponents: [Calendar.Component]=[mode == "month-component" ? .month:.year, .year]
// AX assignment changes the display only. The actual query model consumes
// dates from the control's action, as observed in the real Founder APP.
private var submittedDates=["2026-09-30", "2026-09-30"]
private let left=Element("AXDateTimeArea",100), right=Element("AXDateTimeArea",200)
private let leftStepper=Element("AXIncrementor",156,y:mode == "bezel" ? 84:90,width:20,height:mode == "bezel" ? 24:20)
private let rightStepper=Element("AXIncrementor",256,y:mode == "bezel" ? 84:90,width:20,height:mode == "bezel" ? 24:20)
private let window=Element("AXWindow",0,children:[left,right]), otherWindow=Element("AXWindow",0,children:[left,right])
private let windowBox=Bounds(x:0,y:0,width:1000,height:1000)
private struct Receipt { let windowBounds: Bounds?; let tradeAccountFingerprint: String; let tradeAccountFingerprintCount: Int; let appActive: Bool; let screenLocked: Bool }
private final class Running { let processIdentifier: Int; init(_ pid: Int) { processIdentifier=pid } }
private struct Observation { let primaryWindow: Element?; let receipt: Receipt; let runningApplication: Running? }
private func snapshot(_ changed: Bool=false) -> Observation {
 let fault=changed ? mode.replacingOccurrences(of:"mid-",with:""):""
 return Observation(primaryWindow:fault == "window-change" ? otherWindow:window,
  receipt:Receipt(windowBounds:fault == "bounds-change" ? Bounds(x:20,y:0,width:1000,height:1000):windowBox,
                  tradeAccountFingerprint:fault == "account-change" ? "other":"bound",
                  tradeAccountFingerprintCount:fault == "duplicate-account" ? 2:1,
                  appActive:fault != "inactive", screenLocked:fault == "screen-locked"),
  runningApplication:Running(fault == "pid-change" ? 22:11))
}
private func observe(command: String) -> Observation {
 observations += 1
 if let pending=pendingAction { pendingAction=nil; pending() }
 if actionCount > 0 && !arrowChanged {
  if mode == "mid-duplicate-arrow" { leftStepper.children.append(leftStepper.children[0]); arrowChanged=true }
  if mode == "mid-arrow-move" {
   leftStepper.children[1]=Element("AXButton",leftStepper.box.x+1,subrole:"AXDecrementArrow",y:100,width:19,height:10)
   arrowChanged=true
  }
 }
 return snapshot(observations >= 2 && (!mode.hasPrefix("mid-") || actionCount > 0))
}
private func attribute(_ element: Element, _ key: String) -> AnyObject? {
 if key == kAXChildrenAttribute { return element.children as NSArray }
 if key == kAXValueAttribute { return element.value }
 return nil
}
private func stringAttribute(_ element: Element, _ key: String) -> String {
 return key == kAXRoleAttribute ? element.role:key == kAXSubroleAttribute ? element.subrole:""
}
private func bounds(of element: Element) -> Bounds? { element.box }
private func isSettable(_ element: Element, _ key: String) -> Bool { mode != "not-settable" }
private func CFEqual(_ a: Element, _ b: Element) -> Bool { a === b }
private func CFEqual(_ a: CFTypeRef, _ b: CFTypeRef) -> Bool { (a as! NSObject).isEqual(b) }
private func postSingleLeftClick(at point: CGPoint) -> Bool {
 let stepper=point.x < 200 ? leftStepper:rightStepper
 let index=stepper === leftStepper ? 0:1
 if point.x < stepper.box.x { selectedComponents[index] = .day; return true }
 actionCount += 1
 if mode == "first-step-fails" || mode == "restore-step-fails" && actionCount == 2 { return false }
 if mode == "action-noop" { return true }
 let element=stepper === leftStepper ? left:right
 let formatter=DateFormatter(); formatter.dateFormat="yyyy/M/d"; formatter.timeZone=TimeZone(identifier:"Asia/Shanghai")
 let before=(element.value as? Date) ?? formatter.date(from:element.value as! String)!
 var calendar=Calendar(identifier:.gregorian); calendar.timeZone=formatter.timeZone
 let next=calendar.date(byAdding:selectedComponents[index],value:point.y < 100 ? 1:-1,to:before)!
 let date=min(next,formatter.date(from:"2026/10/10")!)
 let updated: AnyObject=element.value is Date ? date as NSDate:formatter.string(from:date) as NSString
 formatter.dateFormat="yyyy-MM-dd"
 let submitted=formatter.string(from:date)
 let apply={ element.value=updated; submittedDates[stepper === leftStepper ? 0:1]=submitted }
 if mode == "async-action" { pendingAction=apply } else { apply() }
 return true
}
private func AXUIElementSetAttributeValue(_ element: Element, _ key: CFString, _ value: CFTypeRef) -> AXError {
 writes += 1
 if mode == "first-fails" || mode == "second-fails" && writes == 2 { return .failure }
 if mode != "noop" { element.value=value }
 return .success
}
'''
    harness += routine
    harness += r'''
left.children=[leftStepper]; right.children=[rightStepper]
for stepper in [leftStepper,rightStepper] {
 stepper.children=[Element("AXButton",stepper.box.x,subrole:"AXIncrementArrow",y:stepper.box.y,width:20,height:stepper.box.height/2),
                   Element("AXButton",stepper.box.x,subrole:"AXDecrementArrow",y:stepper.box.y+stepper.box.height/2,width:20,height:stepper.box.height/2)]
}
if mode == "missing-stepper" { right.children=[] }
if mode == "duplicate-stepper" { left.children.append(Element("AXIncrementor",130)) }
if mode == "missing-arrow" { leftStepper.children.removeLast() }
if mode == "duplicate-arrow" { leftStepper.children.append(leftStepper.children[0]) }
if mode == "outside-stepper" { leftStepper.children[0]=Element("AXButton",900,subrole:"AXIncrementArrow",width:20,height:10) }
if mode == "date-value" {
 let formatter=DateFormatter(); formatter.dateFormat="yyyy-MM-dd"; formatter.timeZone=TimeZone(identifier:"Asia/Shanghai")
 left.value=formatter.date(from:"2026-09-30")! as NSDate; right.value=left.value
}
if mode == "bad-value" { right.value=NSNumber(value:3) }
if mode == "extra-control" { window.children.append(Element("AXDateTimeArea",280)) }
let target=mode == "bad-target" ? "2026-02-30":mode == "max-date" ? "2026-10-10":"2026-10-09"
let result=setHistoryDates(snapshot(),target:target,fingerprint:"bound")
print(String(data:try! JSONSerialization.data(withJSONObject:["success":result,"writes":writes,"submitted_dates":submittedDates,"actions":actionCount]),encoding:.utf8)!)
'''
    folder = tmp_path_factory.mktemp("history-date-swift")
    path, executable = folder / "dates.swift", folder / "dates"
    path.write_text(harness)
    build = subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, text=True, timeout=45)
    assert build.returncode == 0, build.stderr
    return executable


@pytest.mark.parametrize("mode", ["normal", "date-value", "month-component", "year-component", "async-action", "bezel"])
def test_production_sets_both_string_and_date_controls(history_date_executable, mode):
    result = subprocess.run([str(history_date_executable), mode], capture_output=True, text=True, check=True, timeout=3)
    assert json.loads(result.stdout) == {"success": True, "writes": 2, "submitted_dates": ["2026-10-09", "2026-10-09"], "actions": 4}


def test_picker_maximum_date_commits_without_stepping_into_future(history_date_executable):
    result = subprocess.run([str(history_date_executable), "max-date"], capture_output=True, text=True, check=True, timeout=3)
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["submitted_dates"] == ["2026-10-10", "2026-10-10"]
    assert payload["actions"] == 4


@pytest.mark.parametrize("mode,writes", [("not-settable", 0), ("bad-value", 0), ("extra-control", 0),
    ("bad-target", 0), ("first-fails", 1), ("second-fails", 2), ("noop", 2),
    ("window-change", 1), ("account-change", 1), ("duplicate-account", 1), ("pid-change", 1), ("bounds-change", 1)])
def test_production_date_failure_never_reports_scope_success(history_date_executable, mode, writes):
    result = subprocess.run([str(history_date_executable), mode], capture_output=True, text=True, check=True, timeout=3)
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert payload["writes"] == writes


@pytest.mark.parametrize("mode", ["missing-stepper", "duplicate-stepper", "missing-arrow", "duplicate-arrow", "outside-stepper",
    "first-step-fails", "restore-step-fails", "action-noop"])
def test_date_model_commit_failure_never_authorizes_query(history_date_executable, mode):
    result = subprocess.run([str(history_date_executable), mode], capture_output=True, text=True, check=True, timeout=3)
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    if mode == "action-noop":
        assert payload["actions"] == 1


@pytest.mark.parametrize("fault", ["window-change", "account-change", "duplicate-account", "pid-change", "bounds-change", "inactive", "screen-locked", "duplicate-arrow", "arrow-move"])
def test_identity_change_after_first_step_stops_before_restoration(history_date_executable, fault):
    result = subprocess.run([str(history_date_executable), "mid-" + fault], capture_output=True, text=True, check=True, timeout=3)
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert payload["actions"] == payload["writes"] == 1
