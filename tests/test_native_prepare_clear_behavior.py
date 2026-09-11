"""Execute the production Swift clear routine against reactive AX fields."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_clear_neutralizes_reactive_quote_without_retriggering_code(tmp_path):
    swift = shutil.which("swift")
    if not swift:
        pytest.skip("Swift runtime is required for the native behavior regression")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    start = source.index("private func clearOrderFields")
    end = source.index("private func prepareOrder", start)
    routine = source[start:end].replace("usleep(", "drainReactiveEvents(")
    harness = r'''
import Foundation
import CoreFoundation
private enum Field { case code, price, quantity }
private enum AXResult { case success, failure }
private struct OrderFields {
    let code = Field.code
    let price = Field.price
    let quantity = Field.quantity
}
private let kAXValueAttribute = "AXValue"
private var values: [Field: String] = [.code: "001299", .price: "12.13", .quantity: "1100"]
private var quotePending = false
private var codeWrites = 0
private func AXUIElementSetAttributeValue(_ field: Field, _ attribute: CFString, _ value: CFTypeRef) -> AXResult {
    values[field] = value as? String ?? ""
    if field == .code { quotePending = true; codeWrites += 1 }
    return .success
}
private func drainReactiveEvents(_ delay: UInt32) {
    if quotePending { values[.price] = "11.83"; quotePending = false }
}
private func fieldString(_ field: Field) -> String { values[field] ?? "" }
private func normalizedCode(_ value: String) -> String { value.trimmingCharacters(in: .whitespacesAndNewlines) }
private func normalizedDecimal(_ value: String) -> Double? { Double(value) }
private func normalizedQuantity(_ value: String) -> Int? { Int(value) }
'''
    harness += routine
    harness += r'''
let cleared = clearOrderFields(OrderFields())
if !cleared || values[.code] != "" || values[.price] != "" || values[.quantity] != "" {
    fputs("REACTIVE_QUOTE_NOT_NEUTRALIZED\n", stderr)
    exit(1)
}
if codeWrites != 1 { fputs("CODE_CLEAR_RETRIGGERED\n", stderr); exit(2) }
'''
    path = tmp_path / "clear_behavior.swift"
    path.write_text(harness)
    result = subprocess.run([swift, str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
