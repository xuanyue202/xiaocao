import AppKit
import ApplicationServices
import Foundation

private let schemaVersion = 1
private let helperVersion = 2
private let bundleIdentifier = "com.fzzq.Mac2020"
private let maximumDepth = 12
private let maximumNodes = 1_000
private let messagingTimeoutSeconds: Float = 0.20

private let markerNeedles: [(String, String)] = [
    ("普通交易", "ordinary_trade"),
    ("登录方式", "client_login_method"),
    ("交易密码", "trade_password_label"),
    ("验 证 码", "captcha"),
    ("登 录", "client_login_submit"),
    ("买入下单", "buy_submit"),
    ("卖出下单", "sell_submit"),
    ("证券代码", "security_code"),
    ("买入价格", "buy_price"),
    ("卖出价格", "sell_price"),
    ("买入数量", "buy_quantity"),
    ("卖出数量", "sell_quantity"),
    ("当日委托", "today_orders"),
    ("当日成交", "today_trades"),
    ("持仓", "positions"),
    ("撤单", "cancel")
]

private struct Bounds: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

private struct TableShape: Codable {
    let bounds: Bounds?
    let rowCount: Int
    let columnCount: Int
    let cellCount: Int?
    let readableValueCount: Int?
    let auditComplete: Bool
}

private struct Capabilities: Codable {
    let probe: Bool
    let focusUnlock: Bool
    let keychainUnlockCandidate: Bool
    let focusClientLoginCaptcha: Bool
    let keychainClientLoginFillCandidate: Bool
    let prepare: Bool
    let submit: Bool
    let readPositionValues: Bool
    let unattendedRecoveryProven: Bool
}

private struct ActionResult: Codable {
    let attempted: Bool
    let succeeded: Bool
    let requiresUserInput: Bool
    let confirmPressed: Bool
    let confirmationMode: String
    let unlockPathProven: Bool
}

private struct Receipt: Codable {
    var schemaVersion: Int
    var helperVersion: Int
    var command: String
    var status: String
    var reason: String
    var appRunning: Bool
    var appActive: Bool
    var appHidden: Bool
    var screenLocked: Bool
    var accessibilityTrusted: Bool
    var windowCount: Int
    var mainWindowAvailable: Bool
    var focusedWindowAvailable: Bool
    var windowReadError: Int32
    var windowBounds: Bounds?
    var surfaceState: String
    var side: String
    var nodeCount: Int
    var roleCounts: [String: Int]
    var markers: [String]
    var secureFieldCount: Int
    var confirmButtonCount: Int
    var guardedConfirmAvailable: Bool
    var settableTextFieldCount: Int
    var tableShapes: [TableShape]
    var tradeAccountFingerprint: String
    var tradeAccountFingerprintCount: Int
    var capabilities: Capabilities
    var action: ActionResult?
    var timingMs: Double
}

private struct Observation {
    var receipt: Receipt
    let runningApplication: NSRunningApplication?
    let applicationElement: AXUIElement?
    let primaryWindow: AXUIElement?
    let secureFields: [AXUIElement]
    let clientLoginCaptchaFields: [AXUIElement]
    let confirmButtons: [AXUIElement]
}

private func milliseconds(since start: DispatchTime) -> Double {
    let nanos = DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds
    return (Double(nanos) / 1_000_000.0 * 10).rounded() / 10
}

private func attribute(_ element: AXUIElement, _ name: String) -> AnyObject? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else {
        return nil
    }
    return value
}

private func stringAttribute(_ element: AXUIElement, _ name: String) -> String {
    return attribute(element, name) as? String ?? ""
}

private func elementAttribute(_ element: AXUIElement, _ name: String) -> AXUIElement? {
    guard let raw = attribute(element, name),
          CFGetTypeID(raw) == AXUIElementGetTypeID() else {
        return nil
    }
    return unsafeBitCast(raw, to: AXUIElement.self)
}

private func bounds(of element: AXUIElement) -> Bounds? {
    guard let rawPosition = attribute(element, kAXPositionAttribute),
          CFGetTypeID(rawPosition) == AXValueGetTypeID(),
          let rawSize = attribute(element, kAXSizeAttribute),
          CFGetTypeID(rawSize) == AXValueGetTypeID() else {
        return nil
    }
    var point = CGPoint.zero
    var size = CGSize.zero
    guard AXValueGetValue(unsafeBitCast(rawPosition, to: AXValue.self), .cgPoint, &point),
          AXValueGetValue(unsafeBitCast(rawSize, to: AXValue.self), .cgSize, &size) else {
        return nil
    }
    return Bounds(
        x: Double(point.x),
        y: Double(point.y),
        width: Double(size.width),
        height: Double(size.height)
    )
}

private func isSettable(_ element: AXUIElement, _ name: String) -> Bool {
    var settable = DarwinBoolean(false)
    guard AXUIElementIsAttributeSettable(element, name as CFString, &settable) == .success else {
        return false
    }
    return settable.boolValue
}

private func maskedFingerprint(in value: String) -> String {
    guard let regex = try? NSRegularExpression(pattern: #"\d{8,20}"#) else {
        return ""
    }
    let range = NSRange(value.startIndex..<value.endIndex, in: value)
    guard let match = regex.firstMatch(in: value, range: range),
          let swiftRange = Range(match.range, in: value) else {
        return ""
    }
    let account = String(value[swiftRange])
    guard account.count >= 8 else { return "" }
    return "\(account.prefix(3))******\(account.suffix(3))"
}

private func primaryCoreGraphicsBounds(pid: pid_t) -> Bounds? {
    let rows = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID)
        as? [[String: Any]] ?? []
    return rows.compactMap { row -> Bounds? in
        let owner = (row[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value
        let layer = (row[kCGWindowLayer as String] as? NSNumber)?.intValue
        guard owner == pid, layer == 0,
              let raw = row[kCGWindowBounds as String] as? [String: Any],
              let x = (raw["X"] as? NSNumber)?.doubleValue,
              let y = (raw["Y"] as? NSNumber)?.doubleValue,
              let width = (raw["Width"] as? NSNumber)?.doubleValue,
              let height = (raw["Height"] as? NSNumber)?.doubleValue else {
            return nil
        }
        return Bounds(x: x, y: y, width: width, height: height)
    }.max { left, right in
        left.width * left.height < right.width * right.height
    }
}

private func emptyCapabilities() -> Capabilities {
    return Capabilities(
        probe: true,
        focusUnlock: false,
        keychainUnlockCandidate: false,
        focusClientLoginCaptcha: false,
        keychainClientLoginFillCandidate: false,
        prepare: false,
        submit: false,
        readPositionValues: false,
        unattendedRecoveryProven: false
    )
}

private func emptyReceipt(command: String, status: String, reason: String) -> Receipt {
    return Receipt(
        schemaVersion: schemaVersion,
        helperVersion: helperVersion,
        command: command,
        status: status,
        reason: reason,
        appRunning: false,
        appActive: false,
        appHidden: false,
        screenLocked: false,
        accessibilityTrusted: AXIsProcessTrusted(),
        windowCount: 0,
        mainWindowAvailable: false,
        focusedWindowAvailable: false,
        windowReadError: 0,
        windowBounds: nil,
        surfaceState: status,
        side: "unknown",
        nodeCount: 0,
        roleCounts: [:],
        markers: [],
        secureFieldCount: 0,
        confirmButtonCount: 0,
        guardedConfirmAvailable: false,
        settableTextFieldCount: 0,
        tableShapes: [],
        tradeAccountFingerprint: "",
        tradeAccountFingerprintCount: 0,
        capabilities: emptyCapabilities(),
        action: nil,
        timingMs: 0
    )
}

private func screenLockState() -> Bool? {
    guard let session = CGSessionCopyCurrentDictionary() as? [String: Any] else {
        return nil
    }
    if let value = session["CGSSessionScreenIsLocked"] as? NSNumber {
        return value.boolValue
    }
    if let value = session["CGSSessionScreenIsLocked"] as? Bool {
        return value
    }
    let onConsole = (session[kCGSessionOnConsoleKey as String] as? NSNumber)?.boolValue
        ?? (session[kCGSessionOnConsoleKey as String] as? Bool)
    let loginDone = (session["kCGSessionLoginDoneKey"] as? NSNumber)?.boolValue
        ?? (session["kCGSessionLoginDoneKey"] as? Bool)
    return onConsole == true && loginDone == true ? false : nil
}

private func guardedUnlockConfirmPoint(
    field: Bounds?,
    window: Bounds?
) -> CGPoint? {
    guard let field, let window, window.width > 0, window.height > 0 else {
        return nil
    }
    let normalizedX = (field.x - window.x) / window.width
    let normalizedY = (field.y - window.y) / window.height
    let normalizedWidth = field.width / window.width
    let normalizedHeight = field.height / window.height
    guard (0.35...0.60).contains(normalizedX),
          (0.25...0.55).contains(normalizedY),
          (0.06...0.25).contains(normalizedWidth),
          (0.015...0.060).contains(normalizedHeight) else {
        return nil
    }
    let point = CGPoint(
        x: field.x + min(36, field.width * 0.16),
        y: field.y + field.height + max(20, field.height * 1.05)
    )
    guard point.x >= window.x, point.x <= window.x + window.width,
          point.y >= window.y, point.y <= window.y + window.height else {
        return nil
    }
    return point
}

private func postSingleLeftClick(at point: CGPoint) -> Bool {
    guard let source = CGEventSource(stateID: .combinedSessionState),
          let move = CGEvent(
            mouseEventSource: source,
            mouseType: .mouseMoved,
            mouseCursorPosition: point,
            mouseButton: .left
          ),
          let down = CGEvent(
            mouseEventSource: source,
            mouseType: .leftMouseDown,
            mouseCursorPosition: point,
            mouseButton: .left
          ),
          let up = CGEvent(
            mouseEventSource: source,
            mouseType: .leftMouseUp,
            mouseCursorPosition: point,
            mouseButton: .left
          ) else {
        return false
    }
    let originalPoint = CGEvent(source: nil)?.location
    move.post(tap: .cghidEventTap)
    usleep(30_000)
    down.post(tap: .cghidEventTap)
    usleep(30_000)
    up.post(tap: .cghidEventTap)
    if let originalPoint,
       let restore = CGEvent(
        mouseEventSource: source,
        mouseType: .mouseMoved,
        mouseCursorPosition: originalPoint,
        mouseButton: .left
       ) {
        usleep(30_000)
        restore.post(tap: .cghidEventTap)
    }
    return true
}

private func activateFounder(_ observation: Observation) -> Bool {
    guard let running = observation.runningApplication else { return false }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    process.arguments = ["-b", bundleIdentifier]
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    do {
        try process.run()
        process.waitUntilExit()
    } catch {
        return false
    }
    guard process.terminationStatus == 0 else { return false }
    if let window = observation.primaryWindow {
        _ = AXUIElementPerformAction(window, kAXRaiseAction as CFString)
    }
    let deadline = Date().addingTimeInterval(1)
    while Date() < deadline, !running.isActive {
        Thread.sleep(forTimeInterval: 0.02)
    }
    return running.isActive
}

private func observe(command: String, auditTables: Bool = false) -> Observation {
    let started = DispatchTime.now()
    let trusted = AXIsProcessTrusted()
    guard let running = NSRunningApplication.runningApplications(
        withBundleIdentifier: bundleIdentifier
    ).first else {
        var receipt = emptyReceipt(
            command: command,
            status: "app_absent",
            reason: "Founder Securities process is not running"
        )
        receipt.timingMs = milliseconds(since: started)
        return Observation(
            receipt: receipt,
            runningApplication: nil,
            applicationElement: nil,
            primaryWindow: nil,
            secureFields: [],
            clientLoginCaptchaFields: [],
            confirmButtons: []
        )
    }

    guard let screenLocked = screenLockState() else {
        var receipt = emptyReceipt(
            command: command,
            status: "screen_lock_state_unavailable",
            reason: "macOS login-session lock state could not be proven"
        )
        receipt.appRunning = true
        receipt.appActive = running.isActive
        receipt.appHidden = running.isHidden
        receipt.accessibilityTrusted = trusted
        receipt.windowBounds = primaryCoreGraphicsBounds(pid: running.processIdentifier)
        receipt.timingMs = milliseconds(since: started)
        return Observation(
            receipt: receipt,
            runningApplication: running,
            applicationElement: nil,
            primaryWindow: nil,
            secureFields: [],
            clientLoginCaptchaFields: [],
            confirmButtons: []
        )
    }

    if screenLocked {
        var receipt = emptyReceipt(
            command: command,
            status: "screen_locked",
            reason: "macOS login session is locked"
        )
        receipt.appRunning = true
        receipt.appActive = running.isActive
        receipt.appHidden = running.isHidden
        receipt.screenLocked = true
        receipt.accessibilityTrusted = trusted
        receipt.windowBounds = primaryCoreGraphicsBounds(pid: running.processIdentifier)
        receipt.timingMs = milliseconds(since: started)
        return Observation(
            receipt: receipt,
            runningApplication: running,
            applicationElement: nil,
            primaryWindow: nil,
            secureFields: [],
            clientLoginCaptchaFields: [],
            confirmButtons: []
        )
    }

    guard trusted else {
        var receipt = emptyReceipt(
            command: command,
            status: "accessibility_denied",
            reason: "helper has no existing Accessibility permission"
        )
        receipt.appRunning = true
        receipt.appActive = running.isActive
        receipt.appHidden = running.isHidden
        receipt.screenLocked = false
        receipt.windowBounds = primaryCoreGraphicsBounds(pid: running.processIdentifier)
        receipt.timingMs = milliseconds(since: started)
        return Observation(
            receipt: receipt,
            runningApplication: running,
            applicationElement: nil,
            primaryWindow: nil,
            secureFields: [],
            clientLoginCaptchaFields: [],
            confirmButtons: []
        )
    }

    let application = AXUIElementCreateApplication(running.processIdentifier)
    AXUIElementSetMessagingTimeout(application, messagingTimeoutSeconds)
    var rawWindows: CFTypeRef?
    let windowError = AXUIElementCopyAttributeValue(
        application,
        kAXWindowsAttribute as CFString,
        &rawWindows
    )
    let windows = rawWindows as? [AXUIElement] ?? []
    let mainWindow = elementAttribute(application, kAXMainWindowAttribute)
    let focusedWindow = elementAttribute(application, kAXFocusedWindowAttribute)
    let primaryWindow = mainWindow ?? focusedWindow ?? windows.first
    let roots: [AXUIElement]
    if !windows.isEmpty {
        roots = windows
    } else if let primaryWindow {
        roots = [primaryWindow]
    } else {
        roots = []
    }

    var nodeCount = 1
    var roleCounts: [String: Int] = ["AXApplication": 1]
    var markers = Set<String>()
    var secureFields: [AXUIElement] = []
    var ordinarySettableTextFields: [AXUIElement] = []
    var confirmButtons: [AXUIElement] = []
    var settableTextFieldCount = 0
    var tableShapes: [TableShape] = []
    var tradeFingerprints: [String] = []
    let windowBounds = primaryCoreGraphicsBounds(pid: running.processIdentifier)

    func summarizeTable(_ table: AXUIElement) -> TableShape {
        let rows = attribute(table, kAXRowsAttribute) as? [AXUIElement] ?? []
        let columns = attribute(table, kAXColumnsAttribute) as? [AXUIElement] ?? []
        guard auditTables else {
            return TableShape(
                bounds: bounds(of: table),
                rowCount: rows.count,
                columnCount: columns.count,
                cellCount: nil,
                readableValueCount: nil,
                auditComplete: false
            )
        }
        var cellCount = 0
        var readableValueCount = 0
        for row in rows.prefix(100) {
            let cells = attribute(row, kAXChildrenAttribute) as? [AXUIElement] ?? []
            cellCount += cells.count
            for cell in cells {
                let values = [
                    stringAttribute(cell, kAXTitleAttribute),
                    stringAttribute(cell, kAXDescriptionAttribute),
                    stringAttribute(cell, kAXValueAttribute)
                ]
                if values.contains(where: { !$0.isEmpty }) {
                    readableValueCount += 1
                }
            }
        }
        return TableShape(
            bounds: bounds(of: table),
            rowCount: rows.count,
            columnCount: columns.count,
            cellCount: cellCount,
            readableValueCount: readableValueCount,
            auditComplete: rows.count <= 100
        )
    }

    func walk(_ element: AXUIElement, depth: Int) {
        guard depth <= maximumDepth, nodeCount < maximumNodes else { return }
        nodeCount += 1
        let role = stringAttribute(element, kAXRoleAttribute)
        let normalizedRole = role.isEmpty ? "unknown" : role
        roleCounts[normalizedRole, default: 0] += 1
        let subrole = stringAttribute(element, kAXSubroleAttribute)

        var structuralParts = [
            stringAttribute(element, kAXTitleAttribute),
            stringAttribute(element, kAXDescriptionAttribute),
            stringAttribute(element, kAXHelpAttribute),
            stringAttribute(element, kAXRoleDescriptionAttribute)
        ]
        let valueBearingRoles = Set(["AXStaticText", "AXButton", "AXRadioButton", "AXCheckBox"])
        if valueBearingRoles.contains(role) {
            structuralParts.append(stringAttribute(element, kAXValueAttribute))
        }
        let structuralText = structuralParts.joined(separator: " ")
        for (needle, marker) in markerNeedles where structuralText.contains(needle) {
            markers.insert(marker)
        }

        if role == "AXTextField" {
            if isSettable(element, kAXValueAttribute) {
                settableTextFieldCount += 1
                if subrole != "AXSecureTextField" {
                    ordinarySettableTextFields.append(element)
                }
            }
            if subrole == "AXSecureTextField" {
                secureFields.append(element)
            }
        }
        if role == "AXButton", stringAttribute(element, kAXTitleAttribute) == "确定" {
            confirmButtons.append(element)
        }
        if role == "AXComboBox", let elementBounds = bounds(of: element),
           let windowBounds,
           elementBounds.x > windowBounds.x + windowBounds.width * 0.60 {
            let fingerprint = maskedFingerprint(
                in: stringAttribute(element, kAXValueAttribute)
            )
            if !fingerprint.isEmpty {
                tradeFingerprints.append(fingerprint)
            }
        }
        if role == "AXTable" {
            tableShapes.append(summarizeTable(element))
            return
        }
        if Set(["AXOutline", "AXMenu", "AXMenuBar"]).contains(role) {
            return
        }
        let children = attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
        for child in children {
            walk(child, depth: depth + 1)
        }
    }

    for root in roots {
        walk(root, depth: 0)
    }

    let hasBuy = markers.contains("buy_submit")
    let hasSell = markers.contains("sell_submit")
    let hasClientLogin = markers.contains("client_login_method")
        && markers.contains("trade_password_label")
        && markers.contains("captcha")
        && markers.contains("client_login_submit")
    let surfaceState: String
    let reason: String
    if hasClientLogin, secureFields.count == 1,
       ordinarySettableTextFields.count == 1 {
        surfaceState = "client_login_required"
        reason = "client login password and unique CAPTCHA field are present"
    } else if secureFields.count == 1, !hasBuy, !hasSell {
        surfaceState = "authentication_required"
        reason = "unique secure trade-password control is present"
    } else if (hasBuy != hasSell), settableTextFieldCount >= 3 {
        surfaceState = "trade_ready"
        reason = "unique semantic order surface and editable fields are present"
    } else if markers.contains("positions"), !tableShapes.isEmpty {
        surfaceState = "query_only"
        reason = "query table structure is present without a proven order form"
    } else {
        surfaceState = "incomplete"
        reason = "required semantic controls are incomplete"
    }
    let side = hasBuy && !hasSell ? "buy" : hasSell && !hasBuy ? "sell" : "unknown"
    let fingerprint = tradeFingerprints.count == 1 ? tradeFingerprints[0] : ""
    let canFocusUnlock = surfaceState == "authentication_required"
        && secureFields.count == 1
    let guardedConfirmAvailable = secureFields.count == 1
        && guardedUnlockConfirmPoint(
            field: bounds(of: secureFields[0]),
            window: windowBounds
        ) != nil
    let canKeychainUnlock = canFocusUnlock
        && (confirmButtons.count == 1 || guardedConfirmAvailable)
        && tradeFingerprints.count == 1
    let canFillClientLogin = surfaceState == "client_login_required"
        && secureFields.count == 1
        && ordinarySettableTextFields.count == 1
        && tradeFingerprints.count == 1
    let readablePositionValues = tableShapes.contains { table in
        table.auditComplete && (table.readableValueCount ?? 0) > 0
    }
    let capabilities = Capabilities(
        probe: true,
        focusUnlock: canFocusUnlock,
        keychainUnlockCandidate: canKeychainUnlock,
        focusClientLoginCaptcha: canFillClientLogin,
        keychainClientLoginFillCandidate: canFillClientLogin,
        prepare: false,
        submit: false,
        readPositionValues: readablePositionValues,
        unattendedRecoveryProven: false
    )
    let receipt = Receipt(
        schemaVersion: schemaVersion,
        helperVersion: helperVersion,
        command: command,
        status: surfaceState,
        reason: reason,
        appRunning: true,
        appActive: running.isActive,
        appHidden: running.isHidden,
        screenLocked: false,
        accessibilityTrusted: true,
        windowCount: windows.count,
        mainWindowAvailable: mainWindow != nil,
        focusedWindowAvailable: focusedWindow != nil,
        windowReadError: windowError.rawValue,
        windowBounds: windowBounds,
        surfaceState: surfaceState,
        side: side,
        nodeCount: nodeCount,
        roleCounts: roleCounts,
        markers: markers.sorted(),
        secureFieldCount: secureFields.count,
        confirmButtonCount: confirmButtons.count,
        guardedConfirmAvailable: guardedConfirmAvailable,
        settableTextFieldCount: settableTextFieldCount,
        tableShapes: tableShapes,
        tradeAccountFingerprint: fingerprint,
        tradeAccountFingerprintCount: tradeFingerprints.count,
        capabilities: capabilities,
        action: nil,
        timingMs: milliseconds(since: started)
    )
    return Observation(
        receipt: receipt,
        runningApplication: running,
        applicationElement: application,
        primaryWindow: primaryWindow,
        secureFields: secureFields,
        clientLoginCaptchaFields: ordinarySettableTextFields,
        confirmButtons: confirmButtons
    )
}

private func emit(_ receipt: Receipt) {
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(receipt) else {
        FileHandle.standardError.write(Data("receipt encoding failed\n".utf8))
        exit(70)
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
}

private func option(_ name: String, in arguments: [String]) -> String {
    guard let index = arguments.firstIndex(of: name),
          arguments.indices.contains(index + 1) else {
        return ""
    }
    return arguments[index + 1]
}

private func validFingerprint(_ value: String) -> Bool {
    guard let regex = try? NSRegularExpression(pattern: #"^\d{3}\*{6}\d{3}$"#) else {
        return false
    }
    let range = NSRange(value.startIndex..<value.endIndex, in: value)
    return regex.firstMatch(in: value, range: range) != nil
}

private func readStandardInputSecret() -> String? {
    var data = FileHandle.standardInput.readDataToEndOfFile()
    defer {
        if !data.isEmpty {
            data.resetBytes(in: 0..<data.count)
        }
    }
    while let last = data.last, last == 10 || last == 13 {
        data.removeLast()
    }
    guard !data.isEmpty, data.count <= 128 else { return nil }
    return String(data: data, encoding: .utf8)
}

private func focusUnlock() -> Receipt {
    let observation = observe(command: "focus-unlock")
    var receipt = observation.receipt
    guard receipt.surfaceState == "authentication_required",
          observation.secureFields.count == 1,
          observation.runningApplication != nil else {
        receipt.status = "focus_unlock_unavailable"
        receipt.reason = "a unique locked trade-password field was not proven"
        receipt.action = ActionResult(
            attempted: false,
            succeeded: false,
            requiresUserInput: false,
            confirmPressed: false,
            confirmationMode: "none",
            unlockPathProven: false
        )
        return receipt
    }
    guard activateFounder(observation) else {
        receipt.status = "app_activation_failed"
        receipt.reason = "Founder window could not be proven frontmost"
        receipt.action = ActionResult(
            attempted: true,
            succeeded: false,
            requiresUserInput: false,
            confirmPressed: false,
            confirmationMode: "none",
            unlockPathProven: false
        )
        return receipt
    }
    let focusResult = AXUIElementSetAttributeValue(
        observation.secureFields[0],
        kAXFocusedAttribute as CFString,
        kCFBooleanTrue
    )
    let succeeded = focusResult == .success
    receipt.status = succeeded ? "input_focused" : "focus_failed"
    receipt.reason = succeeded
        ? "trade-password field focused; user input and confirmation are still required"
        : "trade-password field could not be focused"
    receipt.action = ActionResult(
        attempted: true,
        succeeded: succeeded,
        requiresUserInput: succeeded,
        confirmPressed: false,
        confirmationMode: "manual",
        unlockPathProven: false
    )
    return receipt
}

private func fillClientLoginFromStandardInput(arguments: [String]) -> Receipt {
    let initial = observe(command: "fill-client-login-stdin")
    var receipt = initial.receipt
    let expectedFingerprint = option("--expected-fingerprint", in: arguments)
    guard arguments.contains("--allow-stdin-secret") else {
        receipt.status = "client_login_fill_not_explicitly_enabled"
        receipt.reason = "--allow-stdin-secret is required"
        return receipt
    }
    guard validFingerprint(expectedFingerprint),
          receipt.tradeAccountFingerprint == expectedFingerprint,
          receipt.tradeAccountFingerprintCount == 1 else {
        receipt.status = "trade_account_binding_unproven"
        receipt.reason = "unique page and caller trade-account fingerprints did not match"
        return receipt
    }
    guard receipt.surfaceState == "client_login_required",
          initial.secureFields.count == 1,
          initial.clientLoginCaptchaFields.count == 1 else {
        receipt.status = "client_login_surface_unproven"
        receipt.reason = "unique client password and CAPTCHA fields were not proven"
        return receipt
    }
    guard let secret = readStandardInputSecret() else {
        receipt.status = "trade_password_input_invalid"
        receipt.reason = "stdin secret was empty, too long, or not UTF-8"
        return receipt
    }

    guard activateFounder(initial) else {
        receipt.status = "app_activation_failed"
        receipt.reason = "Founder window could not be proven frontmost"
        return receipt
    }
    let setResult = AXUIElementSetAttributeValue(
        initial.secureFields[0],
        kAXValueAttribute as CFString,
        secret as CFTypeRef
    )
    let focusResult = AXUIElementSetAttributeValue(
        initial.clientLoginCaptchaFields[0],
        kAXFocusedAttribute as CFString,
        kCFBooleanTrue
    )
    let succeeded = setResult == .success && focusResult == .success
    receipt.status = succeeded
        ? "client_login_password_filled"
        : "client_login_password_fill_failed"
    receipt.reason = succeeded
        ? "trade password filled and CAPTCHA focused; login was not pressed"
        : "password fill or CAPTCHA focus failed; login was not pressed"
    receipt.action = ActionResult(
        attempted: true,
        succeeded: succeeded,
        requiresUserInput: succeeded,
        confirmPressed: false,
        confirmationMode: "manual_captcha",
        unlockPathProven: false
    )
    return receipt
}

private func unlockFromStandardInput(arguments: [String]) -> Receipt {
    let initial = observe(command: "unlock-stdin")
    var receipt = initial.receipt
    let expectedFingerprint = option("--expected-fingerprint", in: arguments)
    guard arguments.contains("--allow-stdin-secret") else {
        receipt.status = "unlock_not_explicitly_enabled"
        receipt.reason = "--allow-stdin-secret is required"
        return receipt
    }
    guard validFingerprint(expectedFingerprint),
          receipt.tradeAccountFingerprint == expectedFingerprint,
          receipt.tradeAccountFingerprintCount == 1 else {
        receipt.status = "trade_account_binding_unproven"
        receipt.reason = "unique page and caller trade-account fingerprints did not match"
        return receipt
    }
    guard receipt.surfaceState == "authentication_required",
          initial.secureFields.count == 1 else {
        receipt.status = "unlock_surface_unproven"
        receipt.reason = "a unique secure field was not proven"
        return receipt
    }
    let semanticConfirm = initial.confirmButtons.count == 1
        ? initial.confirmButtons[0]
        : nil
    let guardedConfirm = guardedUnlockConfirmPoint(
        field: bounds(of: initial.secureFields[0]),
        window: receipt.windowBounds
    )
    guard semanticConfirm != nil || guardedConfirm != nil else {
        receipt.status = "unlock_confirmation_unproven"
        receipt.reason = "neither a semantic nor guarded coordinate confirmation was proven"
        return receipt
    }
    guard activateFounder(initial) else {
        receipt.status = "app_activation_failed"
        receipt.reason = "Founder window could not be proven frontmost"
        return receipt
    }

    guard let secret = readStandardInputSecret() else {
        receipt.status = "trade_password_input_invalid"
        receipt.reason = "stdin secret was empty, too long, or not UTF-8"
        return receipt
    }

    let setResult = AXUIElementSetAttributeValue(
        initial.secureFields[0],
        kAXValueAttribute as CFString,
        secret as CFTypeRef
    )
    guard setResult == .success else {
        receipt.status = "trade_password_set_failed"
        receipt.reason = "secure-field value could not be set"
        receipt.action = ActionResult(
            attempted: true,
            succeeded: false,
            requiresUserInput: false,
            confirmPressed: false,
            confirmationMode: "none",
            unlockPathProven: false
        )
        return receipt
    }

    let confirmationMode: String
    let confirmSucceeded: Bool
    if let semanticConfirm {
        confirmationMode = "semantic"
        confirmSucceeded = AXUIElementPerformAction(
            semanticConfirm,
            kAXPressAction as CFString
        ) == .success
    } else if let guardedConfirm, initial.runningApplication != nil {
        confirmationMode = "guarded_coordinate"
        confirmSucceeded = postSingleLeftClick(at: guardedConfirm)
    } else {
        confirmationMode = "none"
        confirmSucceeded = false
    }
    guard confirmSucceeded else {
        receipt.status = "unlock_confirm_failed"
        receipt.reason = "the single guarded unlock confirmation could not be pressed"
        receipt.action = ActionResult(
            attempted: true,
            succeeded: false,
            requiresUserInput: false,
            confirmPressed: false,
            confirmationMode: confirmationMode,
            unlockPathProven: false
        )
        return receipt
    }

    let deadline = Date().addingTimeInterval(8)
    var final = observe(command: "unlock-stdin")
    while Date() < deadline, final.receipt.surfaceState != "trade_ready" {
        Thread.sleep(forTimeInterval: 0.10)
        final = observe(command: "unlock-stdin")
    }
    var result = final.receipt
    let proven = result.surfaceState == "trade_ready"
    result.status = proven ? "unlocked" : "unlock_unproven"
    result.reason = proven
        ? "single confirmation produced a semantic trade-ready surface"
        : "single confirmation was pressed but trade readiness was not proven; do not retry automatically"
    result.tradeAccountFingerprint = expectedFingerprint
    result.tradeAccountFingerprintCount = 1
    result.action = ActionResult(
        attempted: true,
        succeeded: proven,
        requiresUserInput: false,
        confirmPressed: true,
        confirmationMode: confirmationMode,
        unlockPathProven: proven
    )
    return result
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard let command = arguments.first else {
    var receipt = emptyReceipt(
        command: "invalid",
        status: "invalid_arguments",
        reason: "expected version, probe, focus-unlock, fill-client-login-stdin, or unlock-stdin"
    )
    receipt.accessibilityTrusted = false
    emit(receipt)
    exit(2)
}

switch command {
case "version":
    var receipt = emptyReceipt(command: "version", status: "ok", reason: "helper available")
    receipt.accessibilityTrusted = AXIsProcessTrusted()
    emit(receipt)
case "probe":
    emit(observe(command: command, auditTables: arguments.contains("--table-audit")).receipt)
case "focus-unlock":
    emit(focusUnlock())
case "fill-client-login-stdin":
    emit(fillClientLoginFromStandardInput(arguments: arguments))
case "unlock-stdin":
    emit(unlockFromStandardInput(arguments: arguments))
default:
    var receipt = emptyReceipt(
        command: command,
        status: "invalid_arguments",
        reason: "unknown command"
    )
    receipt.accessibilityTrusted = false
    emit(receipt)
    exit(2)
}
