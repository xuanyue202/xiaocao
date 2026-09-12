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
private let shape = TableShape(bounds: bounds, rowCount: 3, columnCount: 1, cellCount: 3,
    readableValueCount: 0, auditComplete: mode != "unaudited",
    columns: [TableColumn(title: "买卖标志", bounds: Bounds(x: 0, y: 0, width: 80, height: 90))],
    rowBounds: (0..<3).map { Bounds(x: 0, y: Double($0 * 30), width: 160, height: 30) },
    tableAttributeNames: nil, rowAttributeNames: nil)
private let existing = mode == "preserve" ? [OCRToken(text: "原值", confidence: 0.9,
    bounds: Bounds(x: 10, y: 5, width: 30, height: 15))] : []
private let result = recoverMissingTableText(image: cg, screenBounds: bounds, shapes: [shape], initialTokens: existing)
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
