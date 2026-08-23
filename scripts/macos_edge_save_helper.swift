import AppKit
import ApplicationServices
import Foundation

func emit(_ status: String, _ extra: [String: Any] = [:]) {
    var payload: [String: Any] = ["status": status]
    for (key, value) in extra { payload[key] = value }
    let data = try! JSONSerialization.data(withJSONObject: payload)
    print(String(data: data, encoding: .utf8)!)
    fflush(stdout)
}

func attribute(_ element: AXUIElement, _ name: String) -> AnyObject? {
    var output: CFTypeRef?
    guard AXUIElementCopyAttributeValue(
        element, name as CFString, &output
    ) == .success else { return nil }
    return output as AnyObject?
}

func attributeString(_ element: AXUIElement, _ name: String) -> String {
    return attribute(element, name) as? String ?? ""
}

func descendants(_ root: AXUIElement, limit: Int = 12) -> [AXUIElement] {
    var result: [AXUIElement] = []
    func walk(_ element: AXUIElement, _ depth: Int) {
        if depth > limit { return }
        result.append(element)
        let children = attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
        for child in children { walk(child, depth + 1) }
    }
    walk(root, 0)
    return result
}

func strings(_ root: AXUIElement) -> [String] {
    return descendants(root).flatMap { element in
        [kAXTitleAttribute, kAXValueAttribute, kAXDescriptionAttribute]
            .map { attributeString(element, $0) }
            .filter { !$0.isEmpty }
    }
}

func role(_ element: AXUIElement) -> String {
    return attributeString(element, kAXRoleAttribute)
}

func edgeSheets(_ application: AXUIElement) -> [AXUIElement] {
    let windows = attribute(application, kAXWindowsAttribute) as? [AXUIElement] ?? []
    return windows.flatMap { window in
        descendants(window).filter { role($0) == kAXSheetRole }
    }
}

func button(_ root: AXUIElement, titles: Set<String>) -> AXUIElement? {
    return descendants(root).first {
        role($0) == kAXButtonRole
            && titles.contains(attributeString($0, kAXTitleAttribute))
    }
}

func press(_ element: AXUIElement) -> Bool {
    return AXUIElementPerformAction(element, kAXPressAction as CFString) == .success
}

func postGoToFolder(_ pid: pid_t) -> Bool {
    guard
        let down = CGEvent(
            keyboardEventSource: nil, virtualKey: 5, keyDown: true
        ),
        let up = CGEvent(
            keyboardEventSource: nil, virtualKey: 5, keyDown: false
        )
    else { return false }
    down.flags = [.maskCommand, .maskShift]
    up.flags = [.maskCommand, .maskShift]
    down.postToPid(pid)
    up.postToPid(pid)
    return true
}

let arguments = CommandLine.arguments
guard arguments.count == 4, let expectedSize = Int(arguments[3]) else {
    emit("helper_arguments_invalid")
    exit(2)
}
let expectedName = arguments[1]
let destination = URL(fileURLWithPath: arguments[2]).standardizedFileURL
let destinationDirectory = destination.deletingLastPathComponent()
guard destination.lastPathComponent == expectedName, expectedSize > 0 else {
    emit("helper_target_invalid")
    exit(2)
}
if FileManager.default.fileExists(atPath: destination.path) {
    emit("destination_exists")
    exit(3)
}
guard AXIsProcessTrusted() else {
    emit("accessibility_not_trusted", ["accessibility_trusted": false])
    exit(4)
}
guard let edge = NSRunningApplication.runningApplications(
    withBundleIdentifier: "com.microsoft.edgemac"
).first else {
    emit("edge_not_running", ["accessibility_trusted": true])
    exit(5)
}
let application = AXUIElementCreateApplication(edge.processIdentifier)
emit("ready", ["accessibility_trusted": true])

let overwriteWords = ["replace", "overwrite", "替换", "覆盖", "已存在"]
let deadline = Date().addingTimeInterval(30)
var saveSheet: AXUIElement?
while Date() < deadline {
    for sheet in edgeSheets(application) {
        let values = strings(sheet)
        if values.contains(where: { text in
            overwriteWords.contains(where: {
                text.localizedCaseInsensitiveContains($0)
            })
        }) {
            emit("overwrite_prompt_detected")
            exit(6)
        }
        if values.contains(expectedName) {
            saveSheet = sheet
            break
        }
    }
    if saveSheet != nil { break }
    Thread.sleep(forTimeInterval: 0.1)
}
guard let initialSheet = saveSheet else {
    emit("save_sheet_not_found")
    exit(7)
}
guard strings(initialSheet).contains(expectedName) else {
    emit("save_sheet_filename_mismatch")
    exit(8)
}
guard postGoToFolder(edge.processIdentifier) else {
    emit("go_to_folder_shortcut_failed")
    exit(9)
}

var folderField: AXUIElement?
var folderContainer: AXUIElement?
let folderDeadline = Date().addingTimeInterval(5)
while Date() < folderDeadline {
    for sheet in edgeSheets(application) {
        let fields = descendants(sheet).filter {
            role($0) == kAXTextFieldRole
                && attributeString($0, kAXValueAttribute) != expectedName
        }
        if let field = fields.last {
            folderField = field
            folderContainer = sheet
            break
        }
    }
    if folderField != nil { break }
    Thread.sleep(forTimeInterval: 0.1)
}
guard let field = folderField, let folderSheet = folderContainer else {
    emit("go_to_folder_field_missing")
    exit(10)
}
guard AXUIElementSetAttributeValue(
    field, kAXValueAttribute as CFString, destinationDirectory.path as CFTypeRef
) == .success else {
    emit("go_to_folder_value_failed")
    exit(11)
}
guard let go = button(folderSheet, titles: ["Go", "前往"]), press(go) else {
    emit("go_to_folder_confirm_failed")
    exit(12)
}

var confirmedSheet: AXUIElement?
let confirmationDeadline = Date().addingTimeInterval(5)
while Date() < confirmationDeadline {
    for sheet in edgeSheets(application) {
        let values = strings(sheet)
        if values.contains(expectedName)
            && values.contains(destinationDirectory.lastPathComponent) {
            confirmedSheet = sheet
            break
        }
    }
    if confirmedSheet != nil { break }
    Thread.sleep(forTimeInterval: 0.1)
}
guard let finalSheet = confirmedSheet else {
    emit("save_destination_readback_failed")
    exit(13)
}
let finalStrings = strings(finalSheet)
guard finalStrings.contains(expectedName) else {
    emit("save_sheet_filename_mismatch")
    exit(14)
}
guard !finalStrings.contains(where: { text in
    overwriteWords.contains(where: {
        text.localizedCaseInsensitiveContains($0)
    })
}) else {
    emit("overwrite_prompt_detected")
    exit(15)
}
guard let save = button(finalSheet, titles: ["Save", "存储", "保存"]), press(save) else {
    emit("save_button_failed")
    exit(16)
}

let fileDeadline = Date().addingTimeInterval(10)
while Date() < fileDeadline {
    if let attributes = try? FileManager.default.attributesOfItem(
        atPath: destination.path
    ), let size = attributes[.size] as? NSNumber {
        if size.intValue == expectedSize {
            let handle = try? FileHandle(forReadingFrom: destination)
            let magic = try? handle?.read(upToCount: 5)
            try? handle?.close()
            if magic == Data("%PDF-".utf8) {
                emit("completed", ["actual_size": size.intValue])
                exit(0)
            }
            emit("pdf_magic_invalid")
            exit(17)
        }
        if size.intValue > expectedSize {
            emit("saved_size_mismatch", ["actual_size": size.intValue])
            exit(18)
        }
    }
    Thread.sleep(forTimeInterval: 0.1)
}
emit("saved_file_not_complete")
exit(19)
