"""Run the production secondary-login scanner and reset preparation on AX graphs."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest
pytestmark = [pytest.mark.app_simulation, pytest.mark.app_authentication]

@pytest.fixture(scope='module')
def preparation_executable(tmp_path_factory):
    compiler = shutil.which('swiftc')
    if not compiler:
        pytest.skip('Swift compiler required')
    source = (Path(__file__).resolve().parents[1] / 'native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift').read_text()
    scanner = source[source.index('private struct SecondaryClientLoginNotice'):source.index('private func observe(command:')]
    routines = source[source.index('private func resetFrameChromeWindows('):source.index('private func terminateRejectedSession(')]
    harness = r'''
import Foundation
import CoreFoundation
private let mode=CommandLine.arguments[1], maximumDepth=12, maximumNodes=200
private struct Bounds {let x:Double;let y:Double;let width:Double;let height:Double}
private class Element:NSObject {var area=Bounds(x:0,y:0,width:1000,height:800); var values:[String:Any]=[:]; var children:[Element]=[];var sheets:[Element]=[]
 init(_ role:String,_ title:String="") { values["role"]=role;values["title"]=title }
}
private typealias AXUIElement=Element
private func bounds(of e:Element)->Bounds? {e.area}
private enum AXError {case success,attributeUnsupported,noValue,failure}
private let kAXRoleAttribute="role",kAXTitleAttribute="title",kAXDescriptionAttribute="description",kAXSubroleAttribute="subrole",kAXIdentifierAttribute="identifier",kAXValueAttribute="value",kAXChildrenAttribute="children",kAXWindowsAttribute="windows",kAXParentAttribute="parent",kAXPressAction="press"
private func CFEqual(_ a:Element,_ b:Element)->Bool {a===b}
private func attribute(_ e:Element,_ key:String)->Any? { e.values[key] }
private func stringAttribute(_ e:Element,_ key:String)->String {e.values[key] as? String ?? ""}
private func elementAttribute(_ e:Element,_ key:String)->Element? {e.values[key] as? Element}
private func validFingerprint(_ s:String)->Bool {s=="263******022"}
private func maskedFingerprint(in s:String)->String {s=="263000000022" ? "263******022":"999******999"}
private let primary=Element("AXWindow"), login=Element("AXWindow"),app=Element("AXApplication"),other=Element("AXWindow")
private let secure=Element("AXTextField"),account=Element("AXComboBox"),button=Element("AXButton","确定"),sheet=Element("AXSheet")
private var presses=0,observations=0
private func AXUIElementCopyAttributeValue(_ e:Element,_ key:CFString,_ value:inout CFTypeRef?)->AXError {
 let k=key as String
 if mode=="frame-unreadable-title" && e.values["fixture-frame-button"] as? Bool == true && k=="title" {return .failure}
 if mode=="frame-nonstring-title" && e.values["fixture-frame-button"] as? Bool == true && k=="title" {value=NSNumber(value:7);return .success}
 if (mode=="failed-children" || presses>0 && mode=="late-read-failed" || mode=="late-read-transient" && observations==2) && e===login && k=="children" {return .failure}
 if mode=="wrong-array-type" && e===login && k=="AXSheets" {value="invalid" as NSString;return .success}
 if mode=="late-empty-role" && presses>0 && e===login && k=="role" {value="" as NSString;return .success}
 if k=="children" {value=e.children as NSArray;return .success}
 if k=="AXSheets" {value=e.sheets as NSArray;return .success}
 guard let v=e.values[k] else {return .attributeUnsupported}
 value=v as AnyObject;return .success
}
private func AXUIElementPerformAction(_ e:Element,_ action:CFString)->AXError {
 precondition(e===button);presses += 1
 if mode=="press-failed" {return .failure}
 login.sheets=[]
 if mode=="persistent" {login.sheets=[sheet]}
 if mode=="nested-persistent" {let group=Element("AXGroup");group.sheets=[sheet];login.children.append(group)}
 if mode=="new-modal" {let group=Element("AXGroup");let modal=Element("AXWindow");modal.values["subrole"]="AXDialog";group.children=[modal];primary.children=[group]}
 return .success
}
private class Running {let processIdentifier:Int;init(_ p:Int){processIdentifier=p}}
private struct Receipt {
 var screenLocked:Bool?=false,accessibilityTrusted=true,tradeAccountFingerprint="263******022",tradeAccountFingerprintCount=1,surfaceState="authentication_required",unlockFailureCategory:String?=nil,unlockRemainingAttempts:Int?=nil
}
private struct Observation {let applicationElement:Element?;let primaryWindow:Element?;let runningApplication:Running?;let receipt:Receipt}
if mode=="primary-login-dialog" { primary.values["subrole"]="AXDialog" }
private func observe(command:String)->Observation {
 observations += 1;var r=Receipt();if mode=="primary-login-dialog" {r.surfaceState="client_login_required"}
 let late=presses>0 || mode.hasPrefix("fresh-")
 if late && (mode=="late-account" || mode=="fresh-account") {r.tradeAccountFingerprint="999******999"}
 if mode=="fresh-budget" {r.unlockRemainingAttempts=1}
 if mode=="fresh-locked" {r.screenLocked=true}
 return Observation(applicationElement:app,primaryWindow:late && mode=="late-window" ? other:(mode=="late-primary-transient" && observations==2 ? nil:primary),
 runningApplication:Running(late && mode=="late-pid" ? 22:11),receipt:r)
}
private func dismissLoginSuccessNotice(_ o:Observation,expected:String,allowDismiss:Bool,clearedResetLoginWindow:Element?=nil)->(Bool,Bool,String) {
 // UI geometry/chrome validator is covered separately. AX graphs and reset
 // preparation are production routines here; this stub asserts bound exclusion.
 if let cleared=clearedResetLoginWindow {precondition(cleared===login)}
 return (mode != "unknown-window",false,"")
}
secure.values["subrole"]="AXSecureTextField";account.values["value"]=mode=="wrong-account" ? "999000000999":"263000000022"
button.values["identifier"]=mode=="wrong-button" ? "other":"action-button-1"
sheet.values["description"]="alert"
sheet.children=[Element("AXStaticText",mode=="unknown-text" ? "未知问题":"用户名或密码错误"),button]
login.children=[secure,account]+["登录方式","交易密码","验证码","登录"].map {Element("AXStaticText",$0)}
login.sheets=[sheet];app.values["windows"]=[primary,login]
if mode.hasPrefix("frame-") {
 let frame=Element("AXWindow",mode=="frame-wrong-title" ? "Unexpected":"Window")
 frame.values["subrole"]="AXDialog"
 frame.area=Bounds(x:mode=="frame-wrong-bounds" ? 200:10,y:4,width:66,height:20)
 frame.children=[Element("AXButton",mode=="frame-labeled-button" ? "确定":mode=="frame-empty-button" ? "":"WindowSharingSessionButton")]
 frame.children[0].values["fixture-frame-button"]=true
 frame.children[0].area=Bounds(x:frame.area.x-1,y:frame.area.y-1,width:68,height:22)
 if mode=="frame-extra-control" {frame.children.append(Element("AXTextField"))}
 app.values["windows"]=[primary,login,frame]
}
if mode=="duplicate-sheet" {login.children.append(Element("AXSheet"))}
if mode=="truncated" {var node=login;for _ in 0..<15 {let child=Element("AXGroup");node.children.append(child);node=child}}
'''
    harness += scanner + routines
    harness += r'''
private let initial=Observation(applicationElement:app,primaryWindow:primary,runningApplication:Running(11),receipt:Receipt())
private let result=prepareRejectedSession(initial,expected:"263******022")
print(String(data:try! JSONSerialization.data(withJSONObject:["prepared":result.0 != nil,"attempted":result.1,"acknowledged":resetAlertAcknowledged,"presses":presses,"diagnostic":resetPreparationDiagnostic]),encoding:.utf8)!)
'''
    folder=tmp_path_factory.mktemp('native-reset-preparation')
    path=folder/'fixture.swift';binary=folder/'fixture';path.write_text(harness)
    result=subprocess.run([compiler,str(path),'-o',str(binary)],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stderr
    return binary

@pytest.mark.parametrize('mode,prepared,presses',[
    ('normal',True,1),('frame-normal',True,1),('frame-empty-button',False,1),('frame-unreadable-title',False,1),('frame-nonstring-title',False,1),('frame-wrong-title',False,1),('frame-wrong-bounds',False,1),('frame-labeled-button',False,1),('frame-extra-control',False,1),('primary-login-dialog',True,1),('wrong-account',False,0),('wrong-button',False,0),
    ('unknown-text',False,0),('duplicate-sheet',False,0),('failed-children',False,0),
    ('wrong-array-type',False,0),('truncated',False,0),('fresh-account',False,0),
    ('fresh-budget',False,0),('fresh-locked',False,0),('press-failed',False,1),
    ('persistent',False,1),('nested-persistent',False,1),('new-modal',False,1),
    ('late-empty-role',False,1),('late-read-failed',False,1),('late-read-transient',True,1),('late-primary-transient',True,1),('late-account',False,1),('late-window',False,1),
    ('late-pid',False,1),('unknown-window',False,1)])
def test_actual_scanner_and_preparation(preparation_executable,mode,prepared,presses):
    result=subprocess.run([str(preparation_executable),mode],capture_output=True,text=True,check=True,timeout=4)
    value=json.loads(result.stdout)
    assert value['prepared'] is prepared
    assert value['presses']==presses
    if mode=="late-empty-role":
        assert value["diagnostic"]=="empty_role"


def test_failed_ax_press_preserves_request_without_ack_proof(preparation_executable):
    result=subprocess.run([str(preparation_executable),"press-failed"],capture_output=True,text=True,check=True,timeout=4)
    value=json.loads(result.stdout)
    assert value=={"prepared":False,"attempted":True,"acknowledged":False,"presses":1,"diagnostic":"alert_press_result_unproven"}
