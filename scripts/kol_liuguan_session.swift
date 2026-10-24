// Observe only the existing vendor app. No launch, activation, screenshot or input.
import Cocoa
import ApplicationServices

func attribute(_ element: AXUIElement, _ key: String) -> Any? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(element, key as CFString, &value) == .success ? value : nil
}

func frame(_ element: AXUIElement) -> CGRect? {
    guard let position = attribute(element, kAXPositionAttribute),
          let size = attribute(element, kAXSizeAttribute),
          CFGetTypeID(position as CFTypeRef) == AXValueGetTypeID(),
          CFGetTypeID(size as CFTypeRef) == AXValueGetTypeID() else { return nil }
    var point = CGPoint.zero
    var dimensions = CGSize.zero
    guard AXValueGetValue(position as! AXValue, .cgPoint, &point),
          AXValueGetValue(size as! AXValue, .cgSize, &dimensions) else { return nil }
    return CGRect(origin: point, size: dimensions)
}

func visibleWindows(_ pid: pid_t) -> [[String: Any]] {
    let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], 0) as? [[String: Any]] ?? []
    return windows.filter {
        ($0[kCGWindowOwnerPID as String] as? Int32) == pid &&
        ($0[kCGWindowLayer as String] as? Int) == 0
    }
}

func inspect() -> [String: Any] {
    var result: [String: Any] = [
        "read_only": true, "state": "unknown", "reason": "no_visible_security_prompt",
        "observed_at": ISO8601DateFormatter().string(from: Date())
    ]
    let apps = NSRunningApplication.runningApplications(withBundleIdentifier: "com.tencent.xinWeChat")
        .filter { $0.bundleURL?.path == "/Applications/WeChat.app" }
    guard !apps.isEmpty else {
        result["state"] = "not_running"; result["reason"] = "application_not_running"
        return result
    }
    guard apps.count == 1 else { result["reason"] = "application_binding_not_unique"; return result }
    let pid = apps[0].processIdentifier
    result["pid"] = pid
    guard AXIsProcessTrusted() else { result["reason"] = "ax_unavailable"; return result }
    let app = AXUIElementCreateApplication(pid)
    guard let windows = attribute(app, kAXWindowsAttribute) as? [AXUIElement] else {
        result["reason"] = "ax_unavailable"; return result
    }
    let visible = visibleWindows(pid)
    var cgRows: [[String: Any]] = []
    for candidate in visible {
        guard let bounds = candidate[kCGWindowBounds as String] as? NSDictionary,
              let rect = CGRect(dictionaryRepresentation: bounds),
              let windowID = candidate[kCGWindowNumber as String] as? UInt32 else {
            result["reason"] = "ax_unavailable"; return result
        }
        cgRows.append(["id": windowID, "bounds": [rect.minX, rect.minY, rect.width, rect.height]])
    }
    var axRows: [[String: Any]] = []
    for window in windows {
        guard let rect = frame(window), let minimized = attribute(window, kAXMinimizedAttribute) as? Bool else {
            result["reason"] = "ax_unavailable"; return result
        }
        var queue = [window]
        var index = 0
        var protection = false
        var acknowledgement = false
        while index < queue.count && index < 2000 {
            let element = queue[index]; index += 1
            let role = attribute(element, kAXRoleAttribute) as? String ?? ""
            let strings = [kAXValueAttribute, kAXTitleAttribute, kAXDescriptionAttribute].compactMap {
                attribute(element, $0) as? String
            }
            if role == kAXStaticTextRole && strings.contains("为了你的账号安全，请重新登录。") { protection = true }
            if role == kAXButtonRole && strings.contains("我知道了") { acknowledgement = true }
            queue += attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
        }
        axRows.append(["bounds": [rect.minX, rect.minY, rect.width, rect.height], "minimized": minimized,
                       "security_text": protection, "acknowledgement": acknowledgement])
    }
    // A changing visible set cannot provide a stable binding for this observation.
    let beforeIDs = cgRows.compactMap { $0["id"] as? UInt32 }.sorted()
    let afterIDs = visibleWindows(pid).compactMap { $0[kCGWindowNumber as String] as? UInt32 }.sorted()
    guard beforeIDs == afterIDs else { result["reason"] = "ax_unavailable"; return result }
    result["state"] = "observed"
    result["reason"] = "window_metadata_available"
    result["ax_windows"] = axRows
    result["visible_windows"] = cgRows
    return result
}

let data = try JSONSerialization.data(withJSONObject: inspect(), options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
