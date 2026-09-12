"""Execute production Swift value parsing against order-field corruption."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def numeric_parser(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routines = source[source.index("private func normalizedDecimal"):source.index("private func currentOrderReadback")]
    directory = tmp_path_factory.mktemp("ax-numeric")
    path, executable = directory / "values.swift", directory / "values"
    path.write_text('import Foundation\n' + routines + '''
for value in CommandLine.arguments.dropFirst() {
    if let result = normalizedDecimal(value) {
        print(NSDecimalNumber(decimal: result).stringValue)
    } else { print("INVALID") }
}
''')
    subprocess.run([compiler, str(path), "-o", str(executable)], check=True, capture_output=True, timeout=45)
    return executable


@pytest.mark.parametrize("value,expected", [
    ("10.00", "10"), ("0.349", "0.349"), ("1,100.25", "1100.25"),
    ("￥10.00", "10"), (" 10.00 ", "10"),
    ("10.00garbage", "INVALID"), ("10.00.20", "INVALID"),
    ("1,00.00", "INVALID"), ("10,00", "INVALID"),
    ("1e2", "INVALID"), ("NaN", "INVALID"), ("", "INVALID"),
])
def test_order_decimal_requires_entire_valid_numeric_shape(numeric_parser, value, expected):
    result = subprocess.run([str(numeric_parser), value], capture_output=True, text=True, check=True, timeout=2)
    assert result.stdout.strip() == expected
