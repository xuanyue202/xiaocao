"""Actual Vision recovery from a missing cell, without opening the APP."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def cell_capture(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1]/"native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    parts = [("private struct Bounds:", "private struct Capabilities:"),
             ("private struct OCRToken:", "private func captureFounderWindow("),
             ("private func recognizeText(", "private func redactedOCRLine(")]
    routines = "\n".join(source[source.index(a):source.index(b)] for a,b in parts)
    directory = tmp_path_factory.mktemp("table-capture")
    path, executable = directory/"main.swift", directory/"capture"
    path.write_text("import AppKit\nimport Vision\n"+routines+'''
let image = NSImage(size: NSSize(width: 160, height: 90))
image.lockFocus()
NSColor.black.setFill()
NSRect(x: 0, y: 0, width: 160, height: 90).fill()
for (index, text) in ["买入", "卖出", "已撤"].enumerated() {
    (text as NSString).draw(at: NSPoint(x: 10, y: 67 - index * 30),
        withAttributes: [.font: NSFont.systemFont(ofSize: 16), .foregroundColor: NSColor.yellow])
}
image.unlockFocus()
private let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil)!
private let bounds = Bounds(x: 0, y: 0, width: 160, height: 90)
private let mode = CommandLine.arguments[1]
if mode == "quantity-policy" {
    let raw = CommandLine.arguments[2]
    let readings = CommandLine.arguments.dropFirst(3).map { $0 == "missing" ? nil : Optional($0) }
    print(agreedQuantityCandidateIndex(original: raw, readings: readings) ?? -1)
    exit(0)
}
let quantity = mode.hasPrefix("quantity-")
if quantity {
    image.lockFocus()
    NSColor.black.setFill()
    NSRect(x: 0, y: 0, width: 160, height: 90).fill()
    for index in 0..<3 {
        ("500" as NSString).draw(at: NSPoint(x: 10, y: 67 - index * 30),
            withAttributes: [.font: NSFont.systemFont(ofSize: 16), .foregroundColor: NSColor.green])
    }
    image.unlockFocus()
}
private let sourceImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil)!
private let shape = TableShape(bounds: bounds, rowCount: 3, columnCount: 1, cellCount: 3,
    readableValueCount: 0, auditComplete: !mode.hasSuffix("unaudited"),
    columns: [TableColumn(title: quantity ? "成交数量" : "买卖标志", bounds: Bounds(x: 0, y: 0, width: 80, height: 90))],
    rowBounds: (0..<3).map { Bounds(x: 0, y: Double($0 * 30), width: 160, height: 30) },
    tableAttributeNames: nil, rowAttributeNames: nil)
private let existing = mode == "quantity-empty" ? [] : quantity ? [OCRToken(text: mode == "quantity-conflict" ? "400" : "500.",
    confidence: mode == "quantity-preserve" ? 0.9 : 0.3,
    bounds: Bounds(x: 10, y: 5, width: 30, height: 15))] :
    mode == "preserve" ? [OCRToken(text: "原值", confidence: 0.9,
    bounds: Bounds(x: 10, y: 5, width: 30, height: 15))] : []
private let result = recoverMissingTableText(image: sourceImage, screenBounds: bounds, shapes: [shape], initialTokens: existing)
print(String(data: try JSONEncoder().encode(result), encoding: .utf8)!)
''')
    subprocess.run([compiler, str(path), "-o", str(executable)], capture_output=True, check=True, timeout=45)
    return executable


@pytest.mark.parametrize("mode", ["missing", "preserve", "unaudited"])
def test_cell_crop_preserves_row_geometry_and_existing_readback(cell_capture, mode):
    result = subprocess.run([str(cell_capture), mode], capture_output=True, text=True, check=True, timeout=10)
    tokens = json.loads(result.stdout)
    if mode == "unaudited":
        assert tokens == []
        return
    by_row = {int((x["bounds"]["y"]+x["bounds"]["height"]/2)//30):x["text"] for x in tokens}
    assert by_row == {0: "原值" if mode == "preserve" else "买入", 1: "卖出", 2: "已撤"}


@pytest.mark.parametrize("mode,expected", [("quantity-malformed", "500"), ("quantity-conflict", "400"),
    ("quantity-preserve", "500."), ("quantity-unaudited", "500.")])
def test_filled_quantity_crop_requires_geometry_and_agreement(cell_capture, mode, expected):
    result = subprocess.run([str(cell_capture), mode], capture_output=True, text=True, check=True, timeout=10)
    tokens = json.loads(result.stdout)
    first = next(x for x in tokens if (x["bounds"]["y"]+x["bounds"]["height"]/2) < 30)
    assert first["text"] == expected
    if mode == "quantity-malformed":
        assert first["confidence"] >= 0.5
    if mode == "quantity-conflict":
        assert first["confidence"] == pytest.approx(0.3)


def test_empty_filled_quantity_does_not_acquire_single_crop_authority(cell_capture):
    result = subprocess.run([str(cell_capture), "quantity-empty"], capture_output=True, text=True,
                            check=True, timeout=10)
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize("original,readings,expected", [
    ("500.", ["500", "500.00"], 0),
    ("500", ["500", "500"], 0),
    ("400", ["500", "500"], -1),
    ("500.", ["500", "missing"], -1),
    ("500.", ["500", "600"], -1),
    ("500.", ["500.5", "500.5"], -1),
    ("500.", ["5O0", "5O0"], -1),
    ("500.", ["500.", "500."], -1),
    ("100,00", ["10000", "10000"], -1),
    ("1,100", ["100", "100"], -1),
    ("5O0.", ["500", "500"], -1),
    ("-500", ["500", "500"], -1),
])
def test_filled_quantity_requires_two_strict_integer_reads(cell_capture, original, readings, expected):
    result = subprocess.run([str(cell_capture), "quantity-policy", original, *readings],
                            capture_output=True, text=True, check=True, timeout=10)
    assert int(result.stdout) == expected
