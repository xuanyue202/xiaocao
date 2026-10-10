"""Execute the production refresh seam across identity changes around OCR."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.app_simulation


@pytest.fixture(scope="module")
def refresh_executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routines = source[source.index("private func sameWindowBounds("):source.index("private func historyDateArrowPoints(")]
    routines += source[source.index("private func refreshHistoryQuery("):source.index("private func readQuery(")]
    harness = r'''
import Foundation
private struct Bounds { let x: Double; let y: Double; let width: Double; let height: Double }
private struct HistoryDateRange: Equatable { let start: String; let end: String }
private class Element {}
private let window=Element(), other=Element()
private class Running { let processIdentifier: Int; init(_ pid: Int) { processIdentifier=pid } }
private struct Receipt { let surfaceState: String; let tradeAccountFingerprint: String; let tradeAccountFingerprintCount: Int; let windowBounds: Bounds?; let appActive: Bool; let screenLocked: Bool }
private struct Observation { let primaryWindow: Element?; let runningApplication: Running?; let receipt: Receipt; let dates: HistoryDateRange? }
private struct OCRToken {}
private let mode=CommandLine.arguments[1]
private let target="2026-10-09"
private var clicks=0, reads=0
private func snapshot(_ changed: Bool=false) -> Observation {
 let fault=changed ? mode.replacingOccurrences(of:"before-",with:"").replacingOccurrences(of:"after-",with:"").replacingOccurrences(of:"current-",with:""):""
 return Observation(primaryWindow:fault == "window" ? other:window,
  runningApplication:Running(fault == "pid" ? 22:11),
  receipt:Receipt(surfaceState:fault == "locked" ? "authentication_required":"query_only",
   tradeAccountFingerprint:fault == "account" ? "other":"bound", tradeAccountFingerprintCount:fault == "duplicate" ? 2:1,
   windowBounds:Bounds(x:fault == "bounds" ? 20:0,y:0,width:1000,height:1000),appActive:fault != "inactive",screenLocked:fault == "screen-locked"),
  dates:HistoryDateRange(start:fault == "date" ? "2026-10-08":target,end:target))
}
private func CFEqual(_ a: Element, _ b: Element) -> Bool { a === b }
private func observedHistoryDates(_ o: Observation) -> HistoryDateRange? { o.dates }
private func captureFounderWindow(pid: Int, windowBounds: Bounds) -> (Int,Bounds)? { (1,windowBounds) }
private func recognizeText(image: Int, screenBounds: Bounds) -> [OCRToken] { [] }
private func guardedHistoryRefreshPoint(tokens: [OCRToken], window: Bounds) -> (point: CGPoint?,count: Int) {
 (CGPoint(x:320,y:100),mode == "ambiguous-button" ? 2:1)
}
private func observe(command: String, auditTables: Bool=false) -> Observation {
 reads += 1
 return snapshot(mode.hasPrefix("before-") || mode.hasPrefix("after-") && reads >= 2)
}
private func postSingleLeftClick(at point: CGPoint) -> Bool { clicks += 1; return true }
private func usleep(_ delay: Int) {}
'''
    harness += routines
    harness += r'''
private let result=refreshHistoryQuery(original:snapshot(),current:snapshot(mode.hasPrefix("current-")),fingerprint:"bound",requestedDate:target)
print(String(data:try! JSONSerialization.data(withJSONObject:["success":result != nil,"clicks":clicks]),encoding:.utf8)!)
'''
    folder = tmp_path_factory.mktemp("history-refresh-swift")
    path, executable = folder / "refresh.swift", folder / "refresh"
    path.write_text(harness)
    build = subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, text=True, timeout=45)
    assert build.returncode == 0, build.stderr
    return executable


@pytest.mark.parametrize("stage,expected_clicks", [("current", 0), ("before", 0), ("after", 1)])
@pytest.mark.parametrize("fault", ["account", "duplicate", "pid", "window", "bounds", "date", "locked", "inactive", "screen-locked"])
def test_changed_context_never_proves_history_refresh(refresh_executable, stage, expected_clicks, fault):
    result = subprocess.run([str(refresh_executable), f"{stage}-{fault}"], capture_output=True, text=True, check=True, timeout=3)
    assert json.loads(result.stdout) == {"success": False, "clicks": expected_clicks}


@pytest.mark.parametrize("mode,success,clicks", [("normal", True, 1), ("ambiguous-button", False, 0)])
def test_refresh_requires_unique_button_and_preserves_context(refresh_executable, mode, success, clicks):
    result = subprocess.run([str(refresh_executable), mode], capture_output=True, text=True, check=True, timeout=3)
    assert json.loads(result.stdout) == {"success": success, "clicks": clicks}
