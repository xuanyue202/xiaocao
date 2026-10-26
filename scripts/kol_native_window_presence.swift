// Read-only window metadata. No capture, activation, input, or process enumeration.
import AppKit
import CoreGraphics
import Foundation
let title = CommandLine.arguments.count == 2 ? CommandLine.arguments[1] : ""
guard ["草料二维码", "见势擒龙团"].contains(title) else { exit(2) }
let all = CGWindowListCopyWindowInfo([.optionAll, .excludeDesktopElements], 0) as? [[String: Any]] ?? []
let visible = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], 0) as? [[String: Any]] ?? []
let onScreenIDs = Set(visible.compactMap { $0[kCGWindowNumber as String] as? Int })
let matches = all.filter {
    ($0[kCGWindowName as String] as? String) == title &&
    ($0[kCGWindowOwnerName as String] as? String) == "微信" &&
    ($0[kCGWindowLayer as String] as? Int) == 0
}
var result: [String: Any] = ["match_count": matches.count, "title": title]
if matches.count == 1, let window = matches.first,
   let id = window[kCGWindowNumber as String] as? Int,
   let bounds = window[kCGWindowBounds as String] as? NSDictionary,
   let rect = CGRect(dictionaryRepresentation: bounds) {
    result["window_id"] = id
    result["on_current_screen"] = onScreenIDs.contains(id)
    result["width"] = rect.width
    result["height"] = rect.height
}
let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
