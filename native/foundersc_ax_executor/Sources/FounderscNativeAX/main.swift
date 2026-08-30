import AppKit
import ApplicationServices
import Foundation
import Vision

private let schemaVersion = 2
private let helperVersion = 5
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
    ("撤单", "cancel"),
    ("委托确认", "order_confirmation"),
    ("确认委托", "order_confirmation")
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
    let columns: [TableColumn]?
    let rowBounds: [Bounds]?
    let tableAttributeNames: [String]?
    let rowAttributeNames: [String]?
}

private struct TableColumn: Codable {
    let title: String
    let bounds: Bounds?
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

private struct OrderReadback: Codable {
    let code: String
    let side: String
    let price: String
    let quantity: Int?
    let fieldMappingProven: Bool
    let submitControlCount: Int
    let submitted: Bool
    let saved: Bool
    let started: Bool
    let formCleared: Bool?
    let clickMode: String
    let observedAt: String
}

private struct QueryReadback: Codable {
    let kind: String
    let captureProven: Bool
    let navigationLabelCount: Int
    let navigationClickMode: String
    let headers: [String]
    let rows: [[String: String]]
    let summaryValues: [String: String]
    let rowCount: Int
    let parsingProven: Bool
    let emptyStateProven: Bool
    let ocrLineCount: Int
    let observedAt: String
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
    var orderReadback: OrderReadback?
    var queryReadback: QueryReadback?
    var timingMs: Double
}

private struct OrderFields {
    let code: AXUIElement
    let price: AXUIElement
    let quantity: AXUIElement
}

private struct Observation {
    var receipt: Receipt
    let runningApplication: NSRunningApplication?
    let applicationElement: AXUIElement?
    let primaryWindow: AXUIElement?
    let secureFields: [AXUIElement]
    let clientLoginCaptchaFields: [AXUIElement]
    let confirmButtons: [AXUIElement]
    let orderFields: OrderFields?
    let submitControls: [AXUIElement]
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

private func primaryCoreGraphicsWindowID(pid: pid_t) -> CGWindowID? {
    let rows = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID)
        as? [[String: Any]] ?? []
    return rows.compactMap { row -> (CGWindowID, Double)? in
        let owner = (row[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value
        let layer = (row[kCGWindowLayer as String] as? NSNumber)?.intValue
        let number = (row[kCGWindowNumber as String] as? NSNumber)?.uint32Value
        guard owner == pid, layer == 0, let number,
              let raw = row[kCGWindowBounds as String] as? [String: Any],
              let width = (raw["Width"] as? NSNumber)?.doubleValue,
              let height = (raw["Height"] as? NSNumber)?.doubleValue else {
            return nil
        }
        return (CGWindowID(number), width * height)
    }.max { left, right in left.1 < right.1 }?.0
}

private struct OCRToken {
    let text: String
    let confidence: Float
    let bounds: Bounds
}

private func captureFounderWindow(
    pid: pid_t,
    windowBounds: Bounds
) -> (CGImage, Bounds)? {
    guard let windowID = primaryCoreGraphicsWindowID(pid: pid),
          let image = CGWindowListCreateImage(
            .null,
            .optionIncludingWindow,
            windowID,
            [.boundsIgnoreFraming, .bestResolution]
          ) else {
        return nil
    }
    return (image, windowBounds)
}

private func recognizeText(
    image: CGImage,
    screenBounds: Bounds
) -> [OCRToken] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    guard (try? handler.perform([request])) != nil else { return [] }
    return (request.results ?? []).compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return OCRToken(
            text: candidate.string.trimmingCharacters(in: .whitespacesAndNewlines),
            confidence: candidate.confidence,
            bounds: Bounds(
                x: screenBounds.x + Double(box.minX) * screenBounds.width,
                y: screenBounds.y + Double(1 - box.maxY) * screenBounds.height,
                width: Double(box.width) * screenBounds.width,
                height: Double(box.height) * screenBounds.height
            )
        )
    }.filter { !$0.text.isEmpty }
}

private func redactedOCRLine(_ value: String) -> String {
    guard let regex = try? NSRegularExpression(pattern: #"\d{8,20}"#) else {
        return value
    }
    let range = NSRange(value.startIndex..<value.endIndex, in: value)
    return regex.stringByReplacingMatches(
        in: value,
        range: range,
        withTemplate: "***"
    )
}

private func normalizedHeader(_ value: String) -> String {
    return value
        .replacingOccurrences(of: "↓", with: "")
        .replacingOccurrences(of: "↑", with: "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

private func querySummaryValues(_ tokens: [OCRToken]) -> [String: String] {
    let rendered = tokens.map(\.text).joined(separator: " ")
        .replacingOccurrences(of: ",", with: "")
    let labels = ["余额", "可用", "可取", "股票市值", "资产", "盈亏"]
    var values: [String: String] = [:]
    for label in labels {
        let escaped = NSRegularExpression.escapedPattern(for: label)
        guard let regex = try? NSRegularExpression(
            pattern: "\(escaped)(?:资金)?\\s*[:：]?\\s*([+-]?\\d+(?:\\.\\d+)?)"
        ) else { continue }
        let range = NSRange(rendered.startIndex..<rendered.endIndex, in: rendered)
        guard let match = regex.firstMatch(in: rendered, range: range),
              match.numberOfRanges == 2,
              let valueRange = Range(match.range(at: 1), in: rendered) else {
            continue
        }
        values[label] = String(rendered[valueRange])
    }
    return values
}

private func queryRequiredHeaders(_ kind: String) -> Set<String> {
    switch kind {
    case "positions":
        return ["证券代码", "证券数量", "可卖数量", "当前价"]
    case "today-orders":
        return ["证券代码", "委托时间", "买卖标志", "状态说明", "委托价格", "委托数量", "委托编号", "成交数量"]
    case "today-trades":
        return ["证券代码", "成交时间", "买卖标志", "成交价格", "成交数量", "成交编号", "委托编号"]
    case "funds":
        return ["资金帐号", "资金余额", "可用资金", "总资产"]
    default:
        return []
    }
}

private func structuredQueryReadback(
    kind: String,
    tokens: [OCRToken],
    tableShapes: [TableShape],
    navigationLabelCount: Int,
    navigationClickMode: String
) -> QueryReadback {
    guard tableShapes.count == 1,
          let rawColumns = tableShapes[0].columns,
          let rowBounds = tableShapes[0].rowBounds else {
        return QueryReadback(
            kind: kind,
            captureProven: true,
            navigationLabelCount: navigationLabelCount,
            navigationClickMode: navigationClickMode,
            headers: [],
            rows: [],
            summaryValues: [:],
            rowCount: 0,
            parsingProven: false,
            emptyStateProven: false,
            ocrLineCount: tokens.count,
            observedAt: isoTimestamp()
        )
    }
    let columns = rawColumns.compactMap { column -> TableColumn? in
        let title = normalizedHeader(column.title)
        guard !title.isEmpty, column.bounds != nil else { return nil }
        return TableColumn(title: title, bounds: column.bounds)
    }
    let headers = columns.map(\.title)
    var rows: [[String: String]] = []
    for row in rowBounds {
        let rowTokens = tokens.filter { token in
            let centerY = token.bounds.y + token.bounds.height / 2
            return centerY >= row.y - 2 && centerY <= row.y + row.height + 2
        }
        var values: [String: String] = [:]
        for column in columns {
            guard let columnBounds = column.bounds else { continue }
            let cellTokens = rowTokens.filter { token in
                let centerX = token.bounds.x + token.bounds.width / 2
                return centerX >= columnBounds.x - 2
                    && centerX <= columnBounds.x + columnBounds.width + 2
            }.sorted { $0.bounds.x < $1.bounds.x }
            var value = cellTokens.map(\.text).joined(separator: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if ["股东代码", "资金帐号"].contains(column.title) {
                value = redactedOCRLine(value)
            }
            values[column.title] = value
        }
        if values.values.contains(where: { !$0.isEmpty }) {
            rows.append(values)
        }
    }
    let required = queryRequiredHeaders(kind)
    let headerSet = Set(headers)
    let headersProven = required.isSubset(of: headerSet)
    let emptyMessage = tokens.contains { $0.text.contains("没有相应的查询信息") }
    let emptyStateProven = rowBounds.isEmpty && emptyMessage && headersProven
    let parsingProven = headersProven
        && (emptyStateProven || rows.count == rowBounds.count)
    return QueryReadback(
        kind: kind,
        captureProven: true,
        navigationLabelCount: navigationLabelCount,
        navigationClickMode: navigationClickMode,
        headers: headers,
        rows: rows,
        summaryValues: querySummaryValues(tokens),
        rowCount: rows.count,
        parsingProven: parsingProven,
        emptyStateProven: emptyStateProven,
        ocrLineCount: tokens.count,
        observedAt: isoTimestamp()
    )
}

private func pointForSubstring(_ needle: String, in token: OCRToken) -> CGPoint? {
    guard let range = token.text.range(of: needle), !token.text.isEmpty else {
        return nil
    }
    let total = Double(token.text.count)
    let prefix = Double(token.text[..<range.lowerBound].count)
    let length = Double(token.text[range].count)
    return CGPoint(
        x: token.bounds.x + token.bounds.width * ((prefix + length / 2) / total),
        y: token.bounds.y + token.bounds.height / 2
    )
}

private func guardedOCRConfirmationPoint(
    _ tokens: [OCRToken],
    window: Bounds
) -> CGPoint? {
    let candidates = tokens.filter { token in
        let text = token.text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard ["确认", "确定"].contains(text), token.confidence >= 0.80 else {
            return false
        }
        let normalizedX = (token.bounds.x - window.x) / window.width
        let normalizedY = (token.bounds.y - window.y) / window.height
        let normalizedWidth = token.bounds.width / window.width
        let normalizedHeight = token.bounds.height / window.height
        return (0.25...0.75).contains(normalizedX)
            && (0.25...0.85).contains(normalizedY)
            && (0.01...0.20).contains(normalizedWidth)
            && (0.008...0.10).contains(normalizedHeight)
    }
    guard candidates.count == 1 else { return nil }
    let bounds = candidates[0].bounds
    return CGPoint(
        x: bounds.x + bounds.width / 2,
        y: bounds.y + bounds.height / 2
    )
}

private func queryNavigationTokens(
    _ tokens: [OCRToken],
    label: String,
    windowBounds: Bounds
) -> [OCRToken] {
    return tokens.filter { token in
        let centerX = token.bounds.x + token.bounds.width / 2
        let centerY = token.bounds.y + token.bounds.height / 2
        let normalizedX = (centerX - windowBounds.x) / windowBounds.width
        let normalizedY = (centerY - windowBounds.y) / windowBounds.height
        return token.text.contains(label)
            && token.confidence >= 0.25
            && (0.0...0.95).contains(normalizedX)
            && (0.015...0.65).contains(normalizedY)
    }
}

private func capturedQueryReadback(
    kind: String,
    observation: Observation
) -> QueryReadback? {
    guard let running = observation.runningApplication,
          let windowBounds = observation.receipt.windowBounds,
          let capture = captureFounderWindow(
            pid: running.processIdentifier,
            windowBounds: windowBounds
          ) else {
        return nil
    }
    let tokens = recognizeText(
        image: capture.0,
        screenBounds: capture.1
    )
    return structuredQueryReadback(
        kind: kind,
        tokens: tokens,
        tableShapes: observation.receipt.tableShapes,
        navigationLabelCount: 1,
        navigationClickMode: "ocr_guarded_coordinate"
    )
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
        orderReadback: nil,
        queryReadback: nil,
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

private func exactSemanticText(_ element: AXUIElement, _ expected: String) -> Bool {
    return [
        stringAttribute(element, kAXTitleAttribute),
        stringAttribute(element, kAXDescriptionAttribute),
        stringAttribute(element, kAXValueAttribute),
    ].contains { $0.trimmingCharacters(in: .whitespacesAndNewlines) == expected }
}

private func centerY(_ value: Bounds) -> Double {
    return value.y + value.height / 2
}

private func mapOrderFields(
    side: String,
    textFields: [AXUIElement],
    labels: [String: [AXUIElement]]
) -> OrderFields? {
    guard textFields.count == 3 else { return nil }
    let priceLabel = side == "buy" ? "买入价格" : "卖出价格"
    let quantityLabel = side == "buy" ? "买入数量" : "卖出数量"
    let orderedLabels = ["证券代码", priceLabel, quantityLabel]
    let sortedFields = textFields.compactMap { field -> (AXUIElement, Bounds)? in
        guard let fieldBounds = bounds(of: field) else { return nil }
        return (field, fieldBounds)
    }.sorted { centerY($0.1) < centerY($1.1) }
    guard sortedFields.count == 3 else { return nil }
    if !orderedLabels.allSatisfy({ labels[$0]?.count == 1 }) {
        // Founder 6.12 exposes the three captions as one combined AXStaticText
        // while keeping exactly three vertically ordered editable controls.
        // The surface markers have already proven the side-specific captions;
        // require a strict, compact, same-column field geometry as fallback.
        let centers = sortedFields.map { centerY($0.1) }
        let xValues = sortedFields.map { $0.1.x }
        guard centers[1] - centers[0] >= 8,
              centers[2] - centers[1] >= 8,
              (xValues.max() ?? 0) - (xValues.min() ?? 0) <= 80 else {
            return nil
        }
        return OrderFields(
            code: sortedFields[0].0,
            price: sortedFields[1].0,
            quantity: sortedFields[2].0
        )
    }
    let labelBounds = orderedLabels.compactMap { name in
        labels[name].flatMap { bounds(of: $0[0]) }
    }
    let fieldBounds = textFields.compactMap { bounds(of: $0) }
    guard labelBounds.count == 3, fieldBounds.count == 3 else { return nil }

    let sortedLabels = zip(orderedLabels, labelBounds).sorted {
        centerY($0.1) < centerY($1.1)
    }
    let labelMappedFields = zip(textFields, fieldBounds).sorted {
        centerY($0.1) < centerY($1.1)
    }
    guard sortedLabels.map({ $0.0 }) == orderedLabels else { return nil }
    for index in 0..<3 {
        let label = sortedLabels[index].1
        let field = labelMappedFields[index].1
        let verticalTolerance = max(28.0, max(label.height, field.height) * 1.8)
        guard abs(centerY(label) - centerY(field)) <= verticalTolerance,
              field.x >= label.x,
              field.x - (label.x + label.width) <= 260 else {
            return nil
        }
    }
    return OrderFields(
        code: labelMappedFields[0].0,
        price: labelMappedFields[1].0,
        quantity: labelMappedFields[2].0
    )
}

private func supportsPress(_ element: AXUIElement) -> Bool {
    var raw: CFArray?
    guard AXUIElementCopyActionNames(element, &raw) == .success,
          let actions = raw as? [String] else {
        return false
    }
    return actions.contains(kAXPressAction as String)
}

private func guardedSubmitPoint(
    control: AXUIElement,
    window: Bounds?
) -> CGPoint? {
    guard let controlBounds = bounds(of: control),
          let window, window.width > 0, window.height > 0 else {
        return nil
    }
    let normalizedX = (controlBounds.x - window.x) / window.width
    let normalizedY = (controlBounds.y - window.y) / window.height
    let normalizedWidth = controlBounds.width / window.width
    let normalizedHeight = controlBounds.height / window.height
    guard (0.01...0.55).contains(normalizedX),
          (0.10...0.90).contains(normalizedY),
          (0.02...0.45).contains(normalizedWidth),
          (0.008...0.14).contains(normalizedHeight) else {
        return nil
    }
    return CGPoint(
        x: controlBounds.x + controlBounds.width / 2,
        y: controlBounds.y + controlBounds.height / 2
    )
}

private func isoTimestamp() -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: Date())
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
            confirmButtons: [],
            orderFields: nil,
            submitControls: []
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
            confirmButtons: [],
            orderFields: nil,
            submitControls: []
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
            confirmButtons: [],
            orderFields: nil,
            submitControls: []
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
            confirmButtons: [],
            orderFields: nil,
            submitControls: []
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
    var orderLabels: [String: [AXUIElement]] = [:]
    var buySubmitControls: [AXUIElement] = []
    var sellSubmitControls: [AXUIElement] = []
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
                auditComplete: false,
                columns: nil,
                rowBounds: nil,
                tableAttributeNames: nil,
                rowAttributeNames: nil
            )
        }
        var rawTableAttributes: CFArray?
        let tableAttributes: [String]
        if AXUIElementCopyAttributeNames(table, &rawTableAttributes) == .success {
            tableAttributes = rawTableAttributes as? [String] ?? []
        } else {
            tableAttributes = []
        }
        var rawRowAttributes: CFArray?
        let rowAttributes: [String]
        if let firstRow = rows.first,
           AXUIElementCopyAttributeNames(firstRow, &rawRowAttributes) == .success {
            rowAttributes = rawRowAttributes as? [String] ?? []
        } else {
            rowAttributes = []
        }
        let columnSummaries = columns.map { column in
            TableColumn(
                title: [
                    stringAttribute(column, kAXTitleAttribute),
                    stringAttribute(column, kAXDescriptionAttribute),
                    stringAttribute(column, kAXValueAttribute),
                ].first(where: { !$0.isEmpty }) ?? "",
                bounds: bounds(of: column)
            )
        }
        var headerSummaries: [TableColumn] = []
        if let header = elementAttribute(table, kAXHeaderAttribute) {
            func walkHeader(_ element: AXUIElement, depth: Int) {
                guard depth <= 4 else { return }
                let role = stringAttribute(element, kAXRoleAttribute)
                let title = [
                    stringAttribute(element, kAXTitleAttribute),
                    stringAttribute(element, kAXDescriptionAttribute),
                    stringAttribute(element, kAXValueAttribute),
                ].first(where: { !$0.isEmpty }) ?? ""
                if ["AXButton", "AXSortButton"].contains(role), !title.isEmpty {
                    headerSummaries.append(
                        TableColumn(title: title, bounds: bounds(of: element))
                    )
                    return
                }
                let children = attribute(element, kAXChildrenAttribute)
                    as? [AXUIElement] ?? []
                for child in children {
                    walkHeader(child, depth: depth + 1)
                }
            }
            walkHeader(header, depth: 0)
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
            auditComplete: rows.count <= 100,
            columns: headerSummaries.count == columns.count
                ? headerSummaries : columnSummaries,
            rowBounds: rows.prefix(100).compactMap { bounds(of: $0) },
            tableAttributeNames: tableAttributes.sorted(),
            rowAttributeNames: rowAttributes.sorted()
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
        for label in ["证券代码", "买入价格", "卖出价格", "买入数量", "卖出数量"]
        where exactSemanticText(element, label) {
            orderLabels[label, default: []].append(element)
        }
        if exactSemanticText(element, "买入下单") {
            buySubmitControls.append(element)
        }
        if exactSemanticText(element, "卖出下单") {
            sellSubmitControls.append(element)
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
        if role == "AXButton",
           ["确定", "确认"].contains(
            stringAttribute(element, kAXTitleAttribute)
           ) {
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
    } else if !tableShapes.isEmpty,
              tradeFingerprints.count == 1,
              secureFields.isEmpty,
              settableTextFieldCount == 0 {
        surfaceState = "query_only"
        reason = "account-bound query table is present without an order form"
    } else {
        surfaceState = "incomplete"
        reason = "required semantic controls are incomplete"
    }
    let side = hasBuy && !hasSell ? "buy" : hasSell && !hasBuy ? "sell" : "unknown"
    let orderFields = side == "unknown"
        ? nil
        : mapOrderFields(
            side: side,
            textFields: ordinarySettableTextFields,
            labels: orderLabels
        )
    let submitControls = side == "buy" ? buySubmitControls
        : side == "sell" ? sellSubmitControls : []
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
    let orderCapability = surfaceState == "trade_ready"
        && orderFields != nil
        && submitControls.count == 1
        && tradeFingerprints.count == 1
        && (
            supportsPress(submitControls[0])
            || guardedSubmitPoint(
                control: submitControls[0],
                window: windowBounds
            ) != nil
        )
    let capabilities = Capabilities(
        probe: true,
        focusUnlock: canFocusUnlock,
        keychainUnlockCandidate: canKeychainUnlock,
        focusClientLoginCaptcha: canFillClientLogin,
        keychainClientLoginFillCandidate: canFillClientLogin,
        prepare: orderCapability,
        submit: orderCapability,
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
        orderReadback: nil,
        queryReadback: nil,
        timingMs: milliseconds(since: started)
    )
    return Observation(
        receipt: receipt,
        runningApplication: running,
        applicationElement: application,
        primaryWindow: primaryWindow,
        secureFields: secureFields,
        clientLoginCaptchaFields: ordinarySettableTextFields,
        confirmButtons: confirmButtons,
        orderFields: orderFields,
        submitControls: submitControls
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

private struct OrderInput {
    let code: String
    let side: String
    let priceText: String
    let price: Decimal
    let quantity: Int
    let expectedFingerprint: String
}

private func parseOrderInput(_ arguments: [String]) -> OrderInput? {
    let code = option("--code", in: arguments)
    let side = option("--side", in: arguments).lowercased()
    let rawPrice = option("--price", in: arguments)
    let rawQuantity = option("--quantity", in: arguments)
    let fingerprint = option("--expected-fingerprint", in: arguments)
    guard code.range(of: #"^\d{6}$"#, options: .regularExpression) != nil,
          ["buy", "sell"].contains(side),
          rawPrice.range(
            of: #"^\d{1,6}(?:\.\d{1,3})?$"#,
            options: .regularExpression
          ) != nil,
          let price = Decimal(string: rawPrice, locale: Locale(identifier: "en_US_POSIX")),
          price > 0,
          let quantity = Int(rawQuantity),
          quantity > 0,
          quantity <= 10_000_000,
          validFingerprint(fingerprint) else {
        return nil
    }
    return OrderInput(
        code: code,
        side: side,
        priceText: NSDecimalNumber(decimal: price).stringValue,
        price: price,
        quantity: quantity,
        expectedFingerprint: fingerprint
    )
}

private func fieldString(_ element: AXUIElement) -> String {
    let raw = attribute(element, kAXValueAttribute)
    if let value = raw as? String { return value }
    if let value = raw as? NSNumber { return value.stringValue }
    return ""
}

private func normalizedCode(_ value: String) -> String {
    guard let regex = try? NSRegularExpression(pattern: #"(?<!\d)\d{6}(?!\d)"#) else {
        return ""
    }
    let range = NSRange(value.startIndex..<value.endIndex, in: value)
    let matches = regex.matches(in: value, range: range)
    guard matches.count == 1,
          let swiftRange = Range(matches[0].range, in: value) else {
        return ""
    }
    return String(value[swiftRange])
}

private func normalizedDecimal(_ value: String) -> Decimal? {
    let cleaned = value
        .replacingOccurrences(of: ",", with: "")
        .replacingOccurrences(of: "¥", with: "")
        .replacingOccurrences(of: "￥", with: "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    return Decimal(string: cleaned, locale: Locale(identifier: "en_US_POSIX"))
}

private func normalizedQuantity(_ value: String) -> Int? {
    let cleaned = value
        .replacingOccurrences(of: ",", with: "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
    return Int(cleaned)
}

private func currentOrderReadback(
    input: OrderInput,
    fields: OrderFields,
    submitControlCount: Int,
    submitted: Bool = false,
    saved: Bool = false,
    started: Bool = false,
    formCleared: Bool? = nil,
    clickMode: String = "none"
) -> OrderReadback {
    let code = normalizedCode(fieldString(fields.code))
    let price = normalizedDecimal(fieldString(fields.price))
    let quantity = normalizedQuantity(fieldString(fields.quantity))
    return OrderReadback(
        code: code,
        side: input.side,
        price: price.map { NSDecimalNumber(decimal: $0).stringValue } ?? "",
        quantity: quantity,
        fieldMappingProven: true,
        submitControlCount: submitControlCount,
        submitted: submitted,
        saved: saved,
        started: started,
        formCleared: formCleared,
        clickMode: clickMode,
        observedAt: isoTimestamp()
    )
}

private func orderReadbackMatches(_ readback: OrderReadback, _ input: OrderInput) -> Bool {
    guard readback.code == input.code,
          readback.side == input.side,
          readback.quantity == input.quantity,
          let price = Decimal(
            string: readback.price,
            locale: Locale(identifier: "en_US_POSIX")
          ) else {
        return false
    }
    return price == input.price
}

private func ocrOrderMatches(_ tokens: [OCRToken], _ input: OrderInput) -> Bool {
    let sideText = input.side == "buy" ? "买入" : "卖出"
    let codeMatches = tokens.filter {
        normalizedCode($0.text) == input.code
    }.count
    let priceMatches = tokens.filter {
        normalizedDecimal($0.text) == input.price
    }.count
    let quantityMatches = tokens.filter {
        normalizedQuantity($0.text) == input.quantity
    }.count
    let sideMatches = tokens.filter { $0.text.contains(sideText) }.count
    return codeMatches >= 1
        && priceMatches >= 1
        && quantityMatches >= 1
        && sideMatches >= 1
}

private func validateOrderSurface(
    _ observation: Observation,
    input: OrderInput
) -> String? {
    let receipt = observation.receipt
    guard receipt.surfaceState == "trade_ready",
          receipt.side == input.side,
          receipt.capabilities.prepare,
          receipt.capabilities.submit,
          observation.orderFields != nil,
          observation.submitControls.count == 1 else {
        return "native order surface, fields, side, or submit control were not uniquely proven"
    }
    guard receipt.tradeAccountFingerprintCount == 1,
          receipt.tradeAccountFingerprint == input.expectedFingerprint else {
        return "unique page and caller trade-account fingerprints did not match"
    }
    return nil
}

private func setOrderFields(_ fields: OrderFields, input: OrderInput) -> Bool {
    let codeResult = AXUIElementSetAttributeValue(
        fields.code,
        kAXValueAttribute as CFString,
        input.code as CFTypeRef
    )
    guard codeResult == .success else { return false }
    usleep(20_000)
    let priceResult = AXUIElementSetAttributeValue(
        fields.price,
        kAXValueAttribute as CFString,
        input.priceText as CFTypeRef
    )
    let quantityResult = AXUIElementSetAttributeValue(
        fields.quantity,
        kAXValueAttribute as CFString,
        String(input.quantity) as CFTypeRef
    )
    usleep(20_000)
    return priceResult == .success && quantityResult == .success
}

private func clearOrderFields(_ fields: OrderFields) -> Bool {
    let results = [fields.quantity, fields.price, fields.code].map { field in
        AXUIElementSetAttributeValue(
            field,
            kAXValueAttribute as CFString,
            "" as CFTypeRef
        )
    }
    usleep(20_000)
    let code = normalizedCode(fieldString(fields.code))
    let price = normalizedDecimal(fieldString(fields.price))
    let quantity = normalizedQuantity(fieldString(fields.quantity))
    return results.allSatisfy { $0 == .success }
        && code.isEmpty
        && (price == nil || price == 0)
        && (quantity == nil || quantity == 0)
}

private func prepareOrder(arguments: [String]) -> Receipt {
    let started = DispatchTime.now()
    let initial = observe(command: "prepare-order")
    var receipt = initial.receipt
    guard arguments.contains("--allow-order-prepare"),
          let input = parseOrderInput(arguments) else {
        receipt.status = "prepare_arguments_invalid"
        receipt.reason = "bounded code, side, price, quantity, fingerprint and explicit prepare flag are required"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    if let reason = validateOrderSurface(initial, input: input) {
        receipt.status = "prepare_surface_unproven"
        receipt.reason = reason
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    guard let fields = initial.orderFields,
          activateFounder(initial),
          setOrderFields(fields, input: input) else {
        receipt.status = "prepare_field_set_failed"
        receipt.reason = "one or more order fields could not be set"
        receipt.action = ActionResult(
            attempted: true,
            succeeded: false,
            requiresUserInput: false,
            confirmPressed: false,
            confirmationMode: "none",
            unlockPathProven: false
        )
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    var readback = currentOrderReadback(
        input: input,
        fields: fields,
        submitControlCount: initial.submitControls.count
    )
    guard orderReadbackMatches(readback, input) else {
        _ = clearOrderFields(fields)
        receipt.status = "prepare_readback_mismatch"
        receipt.reason = "exact code, side, price and quantity readback did not match"
        receipt.orderReadback = readback
        receipt.action = ActionResult(
            attempted: true,
            succeeded: false,
            requiresUserInput: false,
            confirmPressed: false,
            confirmationMode: "none",
            unlockPathProven: false
        )
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    let clearAfter = arguments.contains("--clear-after-readback")
    if clearAfter {
        let cleared = clearOrderFields(fields)
        readback = OrderReadback(
            code: readback.code,
            side: readback.side,
            price: readback.price,
            quantity: readback.quantity,
            fieldMappingProven: readback.fieldMappingProven,
            submitControlCount: readback.submitControlCount,
            submitted: false,
            saved: false,
            started: false,
            formCleared: cleared,
            clickMode: "none",
            observedAt: readback.observedAt
        )
        guard cleared else {
            receipt.status = "prepare_clear_unproven"
            receipt.reason = "prepared fields were read back but could not be proven cleared"
            receipt.orderReadback = readback
            receipt.timingMs = milliseconds(since: started)
            return receipt
        }
    }
    receipt.status = "prepared"
    receipt.reason = clearAfter
        ? "exact order fields read back and cleared without submit"
        : "exact order fields read back and left prepared without submit"
    receipt.orderReadback = readback
    receipt.action = ActionResult(
        attempted: true,
        succeeded: true,
        requiresUserInput: false,
        confirmPressed: false,
        confirmationMode: "none",
        unlockPathProven: false
    )
    receipt.timingMs = milliseconds(since: started)
    return receipt
}

private func submitPreparedOrder(arguments: [String]) -> Receipt {
    let started = DispatchTime.now()
    let initial = observe(command: "submit-prepared-order")
    var receipt = initial.receipt
    guard arguments.contains("--allow-single-submit"),
          let input = parseOrderInput(arguments) else {
        receipt.status = "submit_arguments_invalid"
        receipt.reason = "bounded code, side, price, quantity, fingerprint and explicit single-submit flag are required"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    if let reason = validateOrderSurface(initial, input: input) {
        receipt.status = "submit_surface_unproven"
        receipt.reason = reason
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    guard let fields = initial.orderFields else {
        receipt.status = "submit_field_mapping_unproven"
        receipt.reason = "order fields were not uniquely mapped"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    var readback = currentOrderReadback(
        input: input,
        fields: fields,
        submitControlCount: initial.submitControls.count
    )
    guard orderReadbackMatches(readback, input) else {
        receipt.status = "submit_readback_mismatch"
        receipt.reason = "prepared order changed before the final click"
        receipt.orderReadback = readback
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    guard activateFounder(initial) else {
        receipt.status = "app_activation_failed"
        receipt.reason = "Founder window could not be proven frontmost"
        receipt.orderReadback = readback
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    readback = currentOrderReadback(
        input: input,
        fields: fields,
        submitControlCount: initial.submitControls.count
    )
    guard orderReadbackMatches(readback, input) else {
        receipt.status = "submit_readback_changed_after_activation"
        receipt.reason = "prepared order changed after app activation"
        receipt.orderReadback = readback
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }

    let submitControl = initial.submitControls[0]
    let clickMode: String
    let clickSucceeded: Bool
    if supportsPress(submitControl) {
        clickMode = "semantic"
        clickSucceeded = AXUIElementPerformAction(
            submitControl,
            kAXPressAction as CFString
        ) == .success
    } else if let point = guardedSubmitPoint(
        control: submitControl,
        window: receipt.windowBounds
    ) {
        clickMode = "guarded_coordinate"
        clickSucceeded = postSingleLeftClick(at: point)
    } else {
        clickMode = "none"
        clickSucceeded = false
    }
    guard clickSucceeded else {
        readback = OrderReadback(
            code: readback.code,
            side: readback.side,
            price: readback.price,
            quantity: readback.quantity,
            fieldMappingProven: readback.fieldMappingProven,
            submitControlCount: readback.submitControlCount,
            submitted: false,
            saved: false,
            started: false,
            formCleared: nil,
            clickMode: clickMode,
            observedAt: isoTimestamp()
        )
        receipt.status = "submit_click_failed"
        receipt.reason = "the unique submit control could not be pressed"
        receipt.orderReadback = readback
        receipt.action = ActionResult(
            attempted: true,
            succeeded: false,
            requiresUserInput: false,
            confirmPressed: false,
            confirmationMode: clickMode,
            unlockPathProven: false
        )
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }

    usleep(180_000)
    let postClick = observe(command: "submit-prepared-order")
    var confirmationCandidate = postClick.receipt.confirmButtonCount > 0
        || postClick.receipt.windowCount > receipt.windowCount
        || postClick.receipt.markers.contains("order_confirmation")
    var confirmationMarker = postClick.receipt.markers.contains(
        "order_confirmation"
    )
    var confirmationOrderMatched = false
    var ocrConfirmationPoint: CGPoint?
    if let running = postClick.runningApplication,
       let windowBounds = postClick.receipt.windowBounds,
       let capture = captureFounderWindow(
        pid: running.processIdentifier,
        windowBounds: windowBounds
       ) {
        let tokens = recognizeText(
            image: capture.0,
            screenBounds: capture.1
        )
        let rendered = tokens.map(\.text).joined(separator: " ")
        confirmationMarker = confirmationMarker
            || rendered.contains("委托确认")
            || rendered.contains("确认委托")
        confirmationCandidate = confirmationCandidate || confirmationMarker
        confirmationOrderMatched = ocrOrderMatches(tokens, input)
        if confirmationMarker, confirmationOrderMatched {
            ocrConfirmationPoint = guardedOCRConfirmationPoint(
                tokens,
                window: windowBounds
            )
        }
    }
    var brokerConfirmationPressed = false
    var brokerConfirmationMode = "none"
    if confirmationCandidate,
       confirmationMarker,
       confirmationOrderMatched {
        if postClick.confirmButtons.count == 1,
           supportsPress(postClick.confirmButtons[0]) {
            brokerConfirmationMode = "semantic_order_confirmation"
            brokerConfirmationPressed = AXUIElementPerformAction(
                postClick.confirmButtons[0],
                kAXPressAction as CFString
            ) == .success
        } else if let point = ocrConfirmationPoint {
            brokerConfirmationMode = "ocr_guarded_order_confirmation"
            brokerConfirmationPressed = postSingleLeftClick(at: point)
        }
        if brokerConfirmationPressed {
            usleep(120_000)
        }
    }
    let confirmationUnproven = confirmationCandidate
        && !brokerConfirmationPressed
    let submitted = !confirmationUnproven
    readback = OrderReadback(
        code: readback.code,
        side: readback.side,
        price: readback.price,
        quantity: readback.quantity,
        fieldMappingProven: readback.fieldMappingProven,
        submitControlCount: readback.submitControlCount,
        submitted: submitted,
        saved: brokerConfirmationPressed,
        started: true,
        formCleared: nil,
        clickMode: brokerConfirmationPressed
            ? "\(clickMode)+\(brokerConfirmationMode)" : clickMode,
        observedAt: isoTimestamp()
    )
    receipt.status = confirmationUnproven
        ? "submit_confirmation_unproven"
        : brokerConfirmationPressed ? "submit_confirmed" : "submit_clicked"
    receipt.reason = confirmationUnproven
        ? "initial submit was pressed but broker confirmation could not be proven exactly"
        : brokerConfirmationPressed
            ? "exact prepared order received one submit action and one exact broker confirmation"
            : "exact prepared order received one direct submit action; native reconciliation is required"
    receipt.orderReadback = readback
    receipt.action = ActionResult(
        attempted: true,
        succeeded: submitted,
        requiresUserInput: false,
        confirmPressed: brokerConfirmationPressed,
        confirmationMode: brokerConfirmationPressed
            ? brokerConfirmationMode : clickMode,
        unlockPathProven: false
    )
    receipt.timingMs = milliseconds(since: started)
    return receipt
}

private func readQuery(arguments: [String]) -> Receipt {
    let started = DispatchTime.now()
    let initial = observe(command: "read-query")
    var receipt = initial.receipt
    let kind = option("--kind", in: arguments)
    let expectedFingerprint = option("--expected-fingerprint", in: arguments)
    let labelByKind = [
        "positions": "持仓",
        "today-orders": "当日委托",
        "today-trades": "当日成交",
        "funds": "资金明细",
    ]
    guard arguments.contains("--allow-query-navigation"),
          var label = labelByKind[kind],
          validFingerprint(expectedFingerprint) else {
        receipt.status = "query_arguments_invalid"
        receipt.reason = "known query kind, masked account, and explicit query-navigation flag are required"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    if kind == "positions", receipt.surfaceState == "query_only" {
        label = "资金股份"
    }
    guard ["trade_ready", "query_only"].contains(receipt.surfaceState),
          receipt.tradeAccountFingerprintCount == 1,
          receipt.tradeAccountFingerprint == expectedFingerprint,
          activateFounder(initial) else {
        receipt.status = "query_surface_unproven"
        receipt.reason = "unlocked account-bound Founder window could not be activated"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    var finalReadback: QueryReadback?
    var finalReceipt = receipt
    var lastLabelCount = 0
    for _ in 0..<2 {
        let current = observe(command: "read-query")
        guard ["trade_ready", "query_only"].contains(current.receipt.surfaceState),
              current.receipt.tradeAccountFingerprintCount == 1,
              current.receipt.tradeAccountFingerprint == expectedFingerprint,
              let running = current.runningApplication,
              let windowBounds = current.receipt.windowBounds,
              let capture = captureFounderWindow(
                pid: running.processIdentifier,
                windowBounds: windowBounds
              ) else {
            break
        }
        let tokens = recognizeText(
            image: capture.0,
            screenBounds: capture.1
        )
        let labels = queryNavigationTokens(
            tokens,
            label: label,
            windowBounds: windowBounds
        )
        lastLabelCount = labels.count
        guard labels.count == 1,
              let clickPoint = pointForSubstring(label, in: labels[0]),
              postSingleLeftClick(at: clickPoint) else {
            break
        }
        usleep(500_000)
        let finalObservation = observe(command: "read-query", auditTables: true)
        guard ["trade_ready", "query_only"].contains(
            finalObservation.receipt.surfaceState
        ),
              finalObservation.receipt.tradeAccountFingerprintCount == 1,
              finalObservation.receipt.tradeAccountFingerprint
                == expectedFingerprint else {
            break
        }
        finalReceipt = finalObservation.receipt
        finalReadback = capturedQueryReadback(
            kind: kind,
            observation: finalObservation
        )
        if finalReadback?.parsingProven == true {
            break
        }
    }
    receipt = finalReceipt
    guard let queryReadback = finalReadback else {
        receipt.status = "query_navigation_unproven"
        receipt.reason = "the requested read-only query label was not uniquely located or captured"
        receipt.queryReadback = QueryReadback(
            kind: kind,
            captureProven: false,
            navigationLabelCount: lastLabelCount,
            navigationClickMode: "none",
            headers: [],
            rows: [],
            summaryValues: [:],
            rowCount: 0,
            parsingProven: false,
            emptyStateProven: false,
            ocrLineCount: 0,
            observedAt: isoTimestamp()
        )
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    let proven = queryReadback.parsingProven
    receipt.status = proven ? "query_read" : "query_parse_unproven"
    receipt.reason = proven
        ? "same-account Founder query table passed structured local OCR validation"
        : "Founder query capture did not pass structured field validation"
    receipt.action = ActionResult(
        attempted: true,
        succeeded: proven,
        requiresUserInput: false,
        confirmPressed: false,
        confirmationMode: "ocr_guarded_coordinate",
        unlockPathProven: false
    )
    receipt.queryReadback = queryReadback
    receipt.timingMs = milliseconds(since: started)
    return receipt
}

private func openOrderSurface(arguments: [String]) -> Receipt {
    let started = DispatchTime.now()
    let initial = observe(command: "open-order-surface")
    var receipt = initial.receipt
    let side = option("--side", in: arguments).lowercased()
    let expectedFingerprint = option("--expected-fingerprint", in: arguments)
    guard arguments.contains("--allow-readonly-navigation"),
          ["buy", "sell"].contains(side),
          validFingerprint(expectedFingerprint) else {
        receipt.status = "order_navigation_arguments_invalid"
        receipt.reason = "side, masked account, and explicit read-only navigation flag are required"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    guard ["trade_ready", "query_only"].contains(receipt.surfaceState),
          receipt.tradeAccountFingerprintCount == 1,
          receipt.tradeAccountFingerprint == expectedFingerprint else {
        receipt.status = "order_navigation_surface_unproven"
        receipt.reason = "account-bound unlocked Founder surface is required"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    if receipt.surfaceState == "trade_ready", receipt.side == side,
       receipt.capabilities.prepare, receipt.capabilities.submit {
        receipt.status = "order_surface_ready"
        receipt.reason = "requested native order surface was already ready"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    guard activateFounder(initial),
          let running = initial.runningApplication,
          let windowBounds = receipt.windowBounds,
          let capture = captureFounderWindow(
            pid: running.processIdentifier,
            windowBounds: windowBounds
          ) else {
        receipt.status = "order_navigation_capture_unproven"
        receipt.reason = "Founder top navigation could not be captured"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    let label = side == "buy" ? "买入" : "卖出"
    let candidates = recognizeText(
        image: capture.0,
        screenBounds: capture.1
    ).filter { token in
        let centerX = token.bounds.x + token.bounds.width / 2
        let centerY = token.bounds.y + token.bounds.height / 2
        let normalizedX = (centerX - windowBounds.x) / windowBounds.width
        let normalizedY = (centerY - windowBounds.y) / windowBounds.height
        return token.text == label
            && token.confidence >= 0.25
            && (0.0...0.45).contains(normalizedX)
            && (0.0...0.15).contains(normalizedY)
    }
    guard candidates.count == 1,
          let point = pointForSubstring(label, in: candidates[0]),
          postSingleLeftClick(at: point) else {
        receipt.status = "order_navigation_label_unproven"
        receipt.reason = "requested top-level order label was not uniquely located"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    usleep(500_000)
    let final = observe(command: "open-order-surface", auditTables: true)
    var result = final.receipt
    let proven = result.surfaceState == "trade_ready"
        && result.side == side
        && result.tradeAccountFingerprintCount == 1
        && result.tradeAccountFingerprint == expectedFingerprint
        && result.capabilities.prepare
        && result.capabilities.submit
    result.status = proven ? "order_surface_ready" : "order_navigation_unproven"
    result.reason = proven
        ? "requested native order surface was reached without submitting"
        : "top navigation was clicked but requested order surface was not proven"
    result.action = ActionResult(
        attempted: true,
        succeeded: proven,
        requiresUserInput: false,
        confirmPressed: false,
        confirmationMode: "ocr_guarded_coordinate",
        unlockPathProven: false
    )
    result.timingMs = milliseconds(since: started)
    return result
}

private func openQuerySurface(arguments: [String]) -> Receipt {
    let started = DispatchTime.now()
    let initial = observe(command: "open-query-surface")
    var receipt = initial.receipt
    let expectedFingerprint = option("--expected-fingerprint", in: arguments)
    guard arguments.contains("--allow-readonly-navigation"),
          validFingerprint(expectedFingerprint) else {
        receipt.status = "query_surface_arguments_invalid"
        receipt.reason = "masked account and explicit read-only navigation flag are required"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    guard ["trade_ready", "query_only"].contains(receipt.surfaceState),
          receipt.tradeAccountFingerprintCount == 1,
          receipt.tradeAccountFingerprint == expectedFingerprint else {
        receipt.status = "query_surface_navigation_unproven"
        receipt.reason = "account-bound unlocked Founder surface is required"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    if receipt.surfaceState == "query_only" {
        receipt.status = "query_surface_ready"
        receipt.reason = "native query surface was already ready"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    guard activateFounder(initial),
          let running = initial.runningApplication,
          let windowBounds = receipt.windowBounds,
          let capture = captureFounderWindow(
            pid: running.processIdentifier,
            windowBounds: windowBounds
          ) else {
        receipt.status = "query_surface_capture_unproven"
        receipt.reason = "Founder top navigation could not be captured"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    let candidates = recognizeText(
        image: capture.0,
        screenBounds: capture.1
    ).filter { token in
        let centerX = token.bounds.x + token.bounds.width / 2
        let centerY = token.bounds.y + token.bounds.height / 2
        let normalizedX = (centerX - windowBounds.x) / windowBounds.width
        let normalizedY = (centerY - windowBounds.y) / windowBounds.height
        return token.text == "查询"
            && token.confidence >= 0.25
            && (0.0...0.70).contains(normalizedX)
            && (0.0...0.15).contains(normalizedY)
    }
    guard candidates.count == 1,
          let point = pointForSubstring("查询", in: candidates[0]),
          postSingleLeftClick(at: point) else {
        receipt.status = "query_surface_label_unproven"
        receipt.reason = "top-level query label was not uniquely located"
        receipt.timingMs = milliseconds(since: started)
        return receipt
    }
    usleep(500_000)
    let final = observe(command: "open-query-surface", auditTables: true)
    var result = final.receipt
    let proven = result.surfaceState == "query_only"
        && result.tradeAccountFingerprintCount == 1
        && result.tradeAccountFingerprint == expectedFingerprint
    result.status = proven ? "query_surface_ready" : "query_surface_navigation_unproven"
    result.reason = proven
        ? "native full-query surface was reached without submitting"
        : "top query navigation was clicked but query surface was not proven"
    result.action = ActionResult(
        attempted: true,
        succeeded: proven,
        requiresUserInput: false,
        confirmPressed: false,
        confirmationMode: "ocr_guarded_coordinate",
        unlockPathProven: false
    )
    result.timingMs = milliseconds(since: started)
    return result
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
    while Date() < deadline,
          !["trade_ready", "query_only"].contains(
            final.receipt.surfaceState
          ) {
        Thread.sleep(forTimeInterval: 0.10)
        final = observe(command: "unlock-stdin")
    }
    var result = final.receipt
    let proven = ["trade_ready", "query_only"].contains(result.surfaceState)
    result.status = proven ? "unlocked" : "unlock_unproven"
    result.reason = proven
        ? "single confirmation produced an account-bound trade or query surface"
        : "single confirmation was pressed but native readiness was not proven; do not retry automatically"
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
        reason: "expected version, probe, focus-unlock, fill-client-login-stdin, unlock-stdin, prepare-order, submit-prepared-order, read-query, open-order-surface, or open-query-surface"
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
case "prepare-order":
    emit(prepareOrder(arguments: arguments))
case "submit-prepared-order":
    emit(submitPreparedOrder(arguments: arguments))
case "read-query":
    emit(readQuery(arguments: arguments))
case "open-order-surface":
    emit(openOrderSurface(arguments: arguments))
case "open-query-surface":
    emit(openQuerySurface(arguments: arguments))
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
