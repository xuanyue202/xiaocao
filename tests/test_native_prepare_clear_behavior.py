"""Run the production Swift clear routine with deterministic AX fault injection."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def clear_executable(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required for native behavior verification")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routine = source[source.index("private func clearOrderFields"):source.index("private func prepareOrder")]
    harness = r'''
import Foundation
import CoreFoundation
private enum Field { case code, price, quantity }
private typealias AXUIElement = Field
private enum AXResult { case success, failure, cannotComplete }
private typealias AXError = AXResult
private struct OrderFields {
    let code = Field.code
    let price = Field.price
    let quantity = Field.quantity
}
private let kAXValueAttribute = "AXValue"
private let mode = CommandLine.arguments[1]
private var values: [Field: String] = [.code: "001299", .price: "12.13", .quantity: "1100"]
private var elapsed: UInt32 = 0
private var codeWrites = 0
private var priceWrites = 0
private var evidence: [[String: String]] = []
private func simulatedNow() -> Date { Date(timeIntervalSince1970: Double(elapsed) / 1_000_000) }
private var pending: [UInt32] = {
    if mode.hasPrefix("quote-") { return [UInt32(mode.dropFirst(6))! * 1000] }
    if mode == "late-burst" { return [350_000, 600_000] }
    return []
}()
private func AXUIElementSetAttributeValue(_ field: Field, _ attribute: CFString, _ value: CFTypeRef) -> AXResult {
    if mode == "slow-ax" { elapsed += 200_000 }
    guard value as? String == "" else { fatalError("CLEAR_MUST_NOT_SET_AN_ORDER") }
    if field == .code {
        codeWrites += 1
        if mode == "code-write-failed" { return .failure }
    }
    if field == .price {
        priceWrites += 1
        if mode == "write-failed" || (mode == "transient-write" && priceWrites == 1) { return .failure }
    }
    values[field] = ""
    return .success
}
private func drainReactiveEvents(_ delay: UInt32) {
    elapsed += delay
    if mode == "continuous" || pending.contains(where: { $0 <= elapsed }) {
        values[.price] = "11.83"
        pending.removeAll(where: { $0 <= elapsed })
    }
}
private func attribute(_ field: Field, _ name: String) -> AnyObject? {
    if mode == "slow-ax" { elapsed += 200_000 }
    if mode == "slow-ax" && field == .price { return "11.83" as NSString }
    if mode == "read-failed" && field == .price { return nil }
    if mode == "relocked" && elapsed >= 200_000 { return nil }
    if mode == "transient-read" && field == .price && elapsed <= 200_000 { return nil }
    if mode == "wrong-type" && field == .price { return ["unexpected"] as NSArray }
    if mode == "malformed" && field == .price { return "0garbage" as NSString }
    if mode == "quantity-residual" && field == .quantity { return "100" as NSString }
    if mode == "code-residual" && field == .code { return "001299" as NSString }
    if mode == "zero" && field != .code { return NSNumber(value: 0) }
    return (values[field] ?? "") as NSString
}
'''
    harness += routine.replace("usleep(", "drainReactiveEvents(").replace("Date()", "simulatedNow()")
    harness += r'''
let cleared = clearOrderFields(OrderFields()) { evidence.append($0) }
let result: [String: Any] = ["cleared": cleared, "code_writes": codeWrites,
    "elapsed_us": elapsed, "pending_callbacks": pending.count, "evidence": evidence]
let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
'''
    directory = tmp_path_factory.mktemp("native-clear")
    path, executable = directory / "clear.swift", directory / "clear"
    path.write_text(harness)
    compiled = subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, text=True, timeout=45)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    return executable


@pytest.mark.parametrize("mode", ["normal", "quote-100", "quote-200", "quote-300", "quote-350",
                                  "late-burst", "transient-write", "transient-read", "zero"])
def test_clear_recovers_and_observes_quiet_fields(clear_executable, mode):
    result = subprocess.run([str(clear_executable), mode], capture_output=True, text=True, timeout=2, check=True)
    outcome = json.loads(result.stdout)
    assert outcome["cleared"] and outcome["pending_callbacks"] == 0
    assert outcome["code_writes"] == 1  # Repeated code clears would schedule another quote.
    assert outcome["elapsed_us"] <= 1_000_000
    assert all(row["reads_proven"] == "true" for row in outcome["evidence"][-3:])


@pytest.mark.parametrize("mode", ["continuous", "code-write-failed", "write-failed", "read-failed",
                                  "relocked", "wrong-type", "malformed", "quantity-residual", "code-residual"])
def test_clear_never_mistakes_failure_or_residual_for_success(clear_executable, mode):
    result = subprocess.run([str(clear_executable), mode], capture_output=True, text=True, timeout=2, check=True)
    outcome = json.loads(result.stdout)
    assert not outcome["cleared"] and outcome["code_writes"] == 1
    assert outcome["elapsed_us"] <= 1_000_000 and outcome["evidence"]
    if mode in {"read-failed", "relocked", "wrong-type"}:
        assert outcome["evidence"][-1]["reads_proven"] == "false"


def test_clear_bounds_slow_ax_calls(clear_executable):
    result = subprocess.run([str(clear_executable), "slow-ax"], capture_output=True, text=True, timeout=2, check=True)
    outcome = json.loads(result.stdout)
    assert not outcome["cleared"]
    assert outcome["elapsed_us"] <= 3_200_000  # At most one in-flight AX call crosses the budget.
