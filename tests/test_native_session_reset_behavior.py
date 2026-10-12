"""Execute the production fixed-bundle termination guard without an APP."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.app_simulation


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler: pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1]/"native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routine = source[source.index("private func terminateRejectedSession("):source.index("private func readQuery(")]
    routine += source[source.index("private func validFingerprint("):source.index("private func readStandardInputSecret(")]
    harness = r'''
import Foundation
private let bundleIdentifier="com.fzzq.Mac2020"
private let mode=CommandLine.arguments[1]
private struct ActionResult { let attempted:Bool;let succeeded:Bool;let requiresUserInput:Bool;let confirmPressed:Bool;let confirmationMode:String;let unlockPathProven:Bool }
private struct Receipt {
 var action:ActionResult?=nil
 var accessibilityTrusted=true,screenLocked:Bool?=false
 var tradeAccountFingerprintCount=1,tradeAccountFingerprint="263******022"
 var surfaceState="authentication_required",unlockFailureCategory:String?=nil
 var unlockRemainingAttempts:Int?=nil,status="",reason=""
}
private class Window {}
private let window=Window(),other=Window()
private class NSRunningApplication {
 let processIdentifier:Int;var isTerminated=false;var calls=0
 init(_ pid:Int){processIdentifier=pid}
 static func runningApplications(withBundleIdentifier id:String)->[NSRunningApplication]{
  precondition(id==bundleIdentifier)
  return mode == "multiple-apps" ? [app,NSRunningApplication(22)] : [app]
 }
 func terminate()->Bool {calls += 1;isTerminated = mode != "refused";return isTerminated}
}
private let app=NSRunningApplication(11)
private struct Observation { let receipt:Receipt;let runningApplication:NSRunningApplication?;let primaryWindow:Window? }
private var observations=0
private func observe(command:String)->Observation {
 observations += 1
 var r=Receipt()
 let fault=mode.hasPrefix("fresh-") && observations==1 ? "":mode.replacingOccurrences(of:"fresh-",with:"")
 if fault=="locked" {r.screenLocked=true}
 if fault=="unknown-lock" {r.screenLocked=nil}
 if fault=="access" {r.accessibilityTrusted=false}
 if fault=="duplicate" {r.tradeAccountFingerprintCount=2}
 if fault=="account" {r.tradeAccountFingerprint="999******999"}
 if fault=="ready" {r.surfaceState="trade_ready"}
 if fault=="exhausted" {r.unlockRemainingAttempts=1}
 if fault=="account-locked" {r.unlockFailureCategory="account_locked"}
 return Observation(receipt:r,runningApplication:fault=="pid" ? NSRunningApplication(22):app,
  primaryWindow:fault=="window" ? other:window)
}
private func option(_ key:String,in arguments:[String])->String {let i=arguments.firstIndex(of:key)!;return arguments[i+1]}
private func CFEqual(_ a:Window,_ b:Window)->Bool{a===b}
private func usleep(_ delay:Int){}
'''
    harness += routine
    harness += r'''
private var args=["--allow-session-reset","--expected-fingerprint","263******022"]
if mode=="no-enable" {args.removeFirst()}
private let result=terminateRejectedSession(arguments:args)
print(String(data:try! JSONSerialization.data(withJSONObject:["status":result.status,"calls":app.calls,"succeeded":result.action!.succeeded]),encoding:.utf8)!)
'''
    folder=tmp_path_factory.mktemp("session-reset-swift")
    path=folder/"guard.swift";binary=folder/"guard";path.write_text(harness)
    result=subprocess.run([compiler,str(path),"-o",str(binary)],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stderr
    return binary


@pytest.mark.parametrize("mode,calls,success", [
    ("normal",1,True),("refused",1,False),("no-enable",0,False),
    ("multiple-apps",0,False),("locked",0,False),("unknown-lock",0,False),
    ("access",0,False),("duplicate",0,False),("account",0,False),("ready",0,False),
    ("exhausted",0,False),("account-locked",0,False),("pid",0,False),
    ("fresh-locked",0,False),("fresh-pid",0,False),("fresh-window",0,False),
    ("fresh-account",0,False),("fresh-exhausted",0,False),("fresh-account-locked",0,False),
])
def test_only_one_fresh_bound_fixed_app_can_terminate(executable,mode,calls,success):
    result=subprocess.run([str(executable),mode],capture_output=True,text=True,check=True,timeout=4)
    receipt=json.loads(result.stdout)
    assert receipt["calls"]==calls and receipt["succeeded"] is success

@pytest.fixture(scope="module")
def diagnostic_executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler: pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1]/"native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    begin = source.index('            guard let primaryWindow else { continue }', source.index('// Keep modal diagnostics'))
    predicate = source[begin:source.index('            let box = bounds(of: window)', begin)]
    harness = r'''
import Foundation
private class AXUIElement { var parent: AXUIElement?; var sheets: [AXUIElement]=[] }
private let kAXParentAttribute="parent"
private func attribute(_ e:AXUIElement,_ key:String)->AnyObject? { key == "parent" ? e.parent : e.sheets as NSArray }
private func CFEqual(_ a:AnyObject,_ b:AnyObject)->Bool { a === b }
private let target=AXUIElement(), unrelated=AXUIElement(), child=AXUIElement(), sheet=AXUIElement()
child.parent=target; target.sheets=[sheet]
private func bound(_ candidate: AXUIElement, _ primaryWindow: AXUIElement?)->Bool {
 for window in [candidate] {
'''
    harness += predicate
    harness += r'''
  return true
 }
 return false
}
print(String(data:try! JSONSerialization.data(withJSONObject:["target":bound(target,target),"child":bound(child,target),"sheet":bound(sheet,target),"unrelated":bound(unrelated,target),"missing":bound(unrelated,nil)]),encoding:.utf8)!)
'''
    folder=tmp_path_factory.mktemp("target-diagnostic-swift")
    path=folder/"guard.swift";binary=folder/"guard";path.write_text(harness)
    result=subprocess.run([compiler,str(path),"-o",str(binary)],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stderr
    return binary


def test_unrelated_login_window_error_cannot_enter_target_diagnostics(diagnostic_executable):
    result=subprocess.run([str(diagnostic_executable)],capture_output=True,text=True,check=True,timeout=3)
    assert json.loads(result.stdout)=={"target":True,"child":True,"sheet":True,"unrelated":False,"missing":False}
