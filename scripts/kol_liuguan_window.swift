import Cocoa
import ApplicationServices
import CryptoKit

// Confirm the observed control is also visible in the composited desktop.
// Window-only screenshots omit occluding mini-program windows.
func pixelsMatch(_ wid:UInt32,_ rect:CGRect,_ point:CGPoint)->Bool {
    let temp=FileManager.default.temporaryDirectory.appendingPathComponent("liuguan-visible-"+UUID().uuidString)
    do {try FileManager.default.createDirectory(at:temp,withIntermediateDirectories:true)} catch{return false}
    defer {try? FileManager.default.removeItem(at:temp)}
    let full=temp.appendingPathComponent("window.png"),patch=temp.appendingPathComponent("desktop.png")
    let left=Int(floor(point.x))-18,top=Int(floor(point.y))-14
    print("pixel_guard point=\(point.x),\(point.y) rect=\(rect)")
    func capture(_ args:[String])->Bool {
        let p=Process();p.executableURL=URL(fileURLWithPath:"/usr/sbin/screencapture");p.arguments=args
        p.standardOutput=FileHandle.nullDevice
        do {try p.run();p.waitUntilExit();if p.terminationStatus != 0 {print("capture_failed=\(p.terminationStatus)")};return p.terminationStatus==0} catch{print("capture_start_failed");return false}
    }
    guard left>=0,top>=0,
          capture(["-x","-o","-l",String(wid),full.path]),
          capture(["-x","-R\(left),\(top),36,28",patch.path]),
          let wd=try? Data(contentsOf:full),let pd=try? Data(contentsOf:patch),
          let wb=NSBitmapImageRep(data:wd),let pb=NSBitmapImageRep(data:pd) else{print("pixel_guard_capture_or_decode_failed left=\(left) top=\(top)");return false}
    let sx=Double(wb.pixelsWide)/rect.width,sy=Double(wb.pixelsHigh)/rect.height
    guard abs(Double(pb.pixelsWide)/36-sx)<0.01,abs(Double(pb.pixelsHigh)/28-sy)<0.01 else{print("pixel_guard_scale_mismatch window=\(wb.pixelsWide)x\(wb.pixelsHigh) patch=\(pb.pixelsWide)x\(pb.pixelsHigh)");return false}
    let ox=Int(round((Double(left)-rect.minX)*sx)),oy=Int(round((Double(top)-rect.minY)*sy))
    guard ox>=0,oy>=0,ox+pb.pixelsWide<=wb.pixelsWide,oy+pb.pixelsHigh<=wb.pixelsHigh else{return false}
    var difference=0.0;var count=0;var ink=0
    for y in 0..<pb.pixelsHigh {for x in 0..<pb.pixelsWide {
        guard let a=wb.colorAt(x:ox+x,y:oy+y)?.usingColorSpace(NSColorSpace.deviceRGB),let b=pb.colorAt(x:x,y:y)?.usingColorSpace(NSColorSpace.deviceRGB) else{return false}
        difference += Double(abs(a.redComponent-b.redComponent))
        difference += Double(abs(a.greenComponent-b.greenComponent))
        difference += Double(abs(a.blueComponent-b.blueComponent))
        count+=3
        if min(a.redComponent,a.greenComponent,a.blueComponent)<0.9 {ink+=1}
    }}
    let ok=ink>=20 && difference/Double(count)<0.02
    if !ok {
        let evidence=URL(fileURLWithPath:"/Users/bytedance/.codex/yangsheng-capture/native-validation/matrix/input-guard-patch.png")
        try? pd.write(to:evidence)
        print("pixel_guard_mismatch ink=\(ink) mean_difference=\(difference/Double(count))")
    }
    return ok
}

func stop(_ reason:String) -> Never {
    print("{\"input_issued\":false,\"reason\":\"\(reason)\"}"); exit(2)
}
let args=CommandLine.arguments
guard (args.count==6 || args.count==7), let wid=UInt32(args[1]), let pid=Int32(args[2]),
      let rx=Double(args[3]),let ry=Double(args[4]),rx>=0,rx<=1,ry>=0,ry<=1,
      ["--focus","--execute","--focus-execute","--right-click","--copy-link","--type-query","--submit-query","--check","--place-left","--restore-position","--scroll-top"].contains(args[5]) else {stop("invalid_arguments")}
let mode=args[5]
func windows()->[[String:Any]] {
    CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],0) as? [[String:Any]] ?? []
}
func frame(_ w:[String:Any])->CGRect? {
    guard let b=w[kCGWindowBounds as String] as? NSDictionary else{return nil}
    return CGRect(dictionaryRepresentation:b)
}
guard let app=NSRunningApplication(processIdentifier:pid),
      app.bundleURL?.path=="/Applications/WeChat.app",
      let w=windows().first(where:{($0[kCGWindowNumber as String] as? UInt32)==wid}),
      (w[kCGWindowOwnerPID as String] as? Int32)==pid,
      (w[kCGWindowSharingState as String] as? Int)==1,
      let rect=frame(w),let title=w[kCGWindowName as String] as? String else {stop("window_identity_changed")}
let root=AXUIElementCreateApplication(pid)
func attr(_ e:AXUIElement,_ a:String)->CFTypeRef? {
    var value:CFTypeRef?;guard AXUIElementCopyAttributeValue(e,a as CFString,&value) == .success else{return nil};return value
}
func axMatches(_ e:AXUIElement)->Bool {
    guard (attr(e,kAXTitleAttribute) as? String)==title,
      let pv=attr(e,kAXPositionAttribute),let sv=attr(e,kAXSizeAttribute) else{return false}
    var p=CGPoint.zero;var s=CGSize.zero
    guard AXValueGetValue(pv as! AXValue,.cgPoint,&p),AXValueGetValue(sv as! AXValue,.cgSize,&s) else{return false}
    return abs(p.x-rect.minX)<1 && abs(p.y-rect.minY)<1 && abs(s.width-rect.width)<1 && abs(s.height-rect.height)<1
}
guard let axWindows=attr(root,kAXWindowsAttribute) as? [AXUIElement] else{stop("ax_windows_unavailable")}
let matches=axWindows.filter{axMatches($0)}
guard matches.count==1 else{stop("ax_window_ambiguous")}
if mode=="--place-left" || mode=="--restore-position" {
    var position=CGPoint(x:mode=="--place-left" ? -350:20,y:151)
    guard let pv=AXValueCreate(.cgPoint,&position) else{stop("frame_values_unavailable")}
    let pr=AXUIElementSetAttributeValue(matches[0],kAXPositionAttribute as CFString,pv)
    print("{\"window_id\":\(wid),\"position_result\":\(pr.rawValue),\"mouse_input_issued\":false}");exit(0)
}
if ["--focus","--focus-execute","--right-click","--scroll-top","--copy-link","--type-query","--submit-query"].contains(mode) {
    app.activate(options:[])
    guard AXUIElementPerformAction(matches[0],kAXRaiseAction as CFString) == .success else{stop("raise_failed")}
    if mode=="--focus" {print("{\"focus_requested\":true,\"mouse_input_issued\":false,\"window_id\":\(wid)}");exit(0)}
    let deadline=Date().addingTimeInterval(0.5)
    while NSWorkspace.shared.frontmostApplication?.processIdentifier != pid && Date()<deadline {
        RunLoop.current.run(until:Date().addingTimeInterval(0.016))
    }
}
guard NSWorkspace.shared.frontmostApplication?.processIdentifier==pid else{stop("application_not_frontmost")}
// A mouse click is bound by the exact topmost CG window at the point.
// Qt may omit AXFocusedWindow entirely. If it supplies one, reject a mismatch.
if let focused=attr(root,kAXFocusedWindowAttribute), !axMatches(focused as! AXUIElement) {stop("focused_window_mismatch")}
let point=CGPoint(x:rect.minX+rect.width*rx,y:rect.minY+rect.height*ry)
guard let top=windows().first(where:{if let r=frame($0){return r.width>1 && r.height>1 && r.contains(point)};return false}) else{stop("point_no_window")}
if (top[kCGWindowNumber as String] as? UInt32) != wid {
    // macOS Dock may own a transparent full-screen surface. Resolve the actual
    // input target through the system AX hit test, rather than ignore overlays.
    var hit:AXUIElement?
    let hitStatus=AXUIElementCopyElementAtPosition(AXUIElementCreateSystemWide(),Float(point.x),Float(point.y),&hit)
    var verifiedHit=false
    if hitStatus == .success, let element=hit {
        var hitPid:pid_t=0
        if AXUIElementGetPid(element,&hitPid) == .success && hitPid==pid {
            if axMatches(element) {verifiedHit=true}
            else if let hw=attr(element,kAXWindowAttribute) {verifiedHit=axMatches(hw as! AXUIElement)}
        }
    }
    if !verifiedHit && !pixelsMatch(wid,rect,point) {
    let detail:[String:Any] = ["input_issued":false,"reason":"point_occluded","covering_window_id":top[kCGWindowNumber as String] ?? 0,"covering_pid":top[kCGWindowOwnerPID as String] ?? 0,"covering_title":top[kCGWindowName as String] ?? "","covering_alpha":top[kCGWindowAlpha as String] ?? -1]
    let d=try! JSONSerialization.data(withJSONObject:detail,options:[.sortedKeys]);print(String(data:d,encoding:.utf8)!);exit(2)
    }
}
if mode=="--check" {print("{\"verified\":true,\"input_issued\":false,\"window_id\":\(wid)}");exit(0)}
if mode=="--scroll-top" {
    guard let e=CGEvent(scrollWheelEvent2Source:nil,units:.pixel,wheelCount:1,wheel1:10000,wheel2:0,wheel3:0) else{stop("scroll_event_unavailable")}
    e.location=point;e.post(tap:.cghidEventTap)
    print("{\"scroll_submitted\":true,\"window_id\":\(wid)}");exit(0)
}
let pasteboard=NSPasteboard.general
let previousChange=pasteboard.changeCount
let previousItems=mode=="--copy-link" ? (pasteboard.pasteboardItems ?? []).map{item in item.types.reduce(into:[NSPasteboard.PasteboardType:Data]()){if let d=item.data(forType:$1){$0[$1]=d}}}:[]
let right=mode=="--right-click"
for t:CGEventType in right ? [.rightMouseDown,.rightMouseUp]:[.leftMouseDown,.leftMouseUp] {
    guard let e=CGEvent(mouseEventSource:nil,mouseType:t,mouseCursorPosition:point,mouseButton:right ? .right:.left) else{stop("event_creation_failed")}
    e.post(tap:.cghidEventTap)
}
if mode=="--type-query" || mode=="--submit-query" {
    RunLoop.current.run(until:Date().addingTimeInterval(0.06))
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier==pid else{stop("focus_changed_before_typing")}
    if mode=="--type-query" {
        guard args.count==7,args[6].count>0,args[6].count<=100,!args[6].contains("://") else{stop("invalid_query")}
        let units=Array(args[6].utf16)
        units.withUnsafeBufferPointer{buffer in
            for down in [true,false] {
                let event=CGEvent(keyboardEventSource:nil,virtualKey:0,keyDown:down)!
                event.keyboardSetUnicodeString(stringLength:units.count,unicodeString:buffer.baseAddress!)
                event.post(tap:.cghidEventTap)
            }
        }
    } else {
        for down in [true,false] {CGEvent(keyboardEventSource:nil,virtualKey:36,keyDown:down)!.post(tap:.cghidEventTap)}
    }
    print("{\"input_issued\":true,\"query_action_submitted\":true}");exit(0)
}
if mode=="--copy-link" {
    let deadline=Date().addingTimeInterval(1)
    while pasteboard.changeCount==previousChange && Date()<deadline {RunLoop.current.run(until:Date().addingTimeInterval(0.016))}
    let copiedChange=pasteboard.changeCount
    guard copiedChange != previousChange, let copied=pasteboard.string(forType:.string) else{print("{\"input_issued\":true,\"copy_verified\":false}");exit(2)}
    var report:[String:Any] = ["input_issued":true,"copy_verified":true,"url_sha256":SHA256.hash(data:Data(copied.utf8)).map{String(format:"%02x",$0)}.joined()]
    if let url=URLComponents(string:copied.trimmingCharacters(in:.whitespacesAndNewlines)) {
        report["scheme"]=url.scheme ?? "";report["host"]=url.host ?? "";report["path"]=url.path
        report["query_keys"]=(url.queryItems ?? []).map{$0.name}.sorted()
        report["stable_identity_fields"]=(url.queryItems ?? []).filter{["objectId","feedId","eid","encryptedObjectId","finderUsername","username"].contains($0.name)}.reduce(into:[String:String]()){$0[$1.name]=$1.value ?? ""}
    }
    if pasteboard.changeCount==copiedChange {
        pasteboard.clearContents()
        let restored=previousItems.map {stored -> NSPasteboardItem in let item=NSPasteboardItem();for (type,data) in stored {item.setData(data,forType:type)};return item}
        pasteboard.writeObjects(restored);report["clipboard_restored"]=true
    } else {report["clipboard_restored"]=false}
    let data=try! JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]);print(String(data:data,encoding:.utf8)!);exit(0)
}
print("{\"input_issued\":true,\"window_id\":\(wid),\"x\":\(point.x),\"y\":\(point.y)}")
