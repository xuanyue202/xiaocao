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


@pytest.fixture(scope="module")
def cell_parser(tmp_path_factory):
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routine = source[source.index("private func queryCellText("):source.index("private func structuredQueryReadback(")]
    directory = tmp_path_factory.mktemp("ax-cell")
    path, executable = directory / "cell.swift", directory / "cell"
    path.write_text('import Foundation\n' + routine + '\nprint(queryCellText(title: CommandLine.arguments[1], fragments: Array(CommandLine.arguments.dropFirst(2))))\n')
    subprocess.run([compiler, str(path), "-o", str(executable)], check=True, capture_output=True, timeout=45)
    return executable


@pytest.mark.parametrize("title,fragments,expected", [
    ("委托编号", ["600", "0009"], "6000009"),
    ("委托编号", ["600 0009"], "6000009"),
    ("成交编号", ["000", "123"], "000123"),
    ("证券代码", ["512", "010"], "512010"),
    ("委托编号", ["6O0", "0009"], "6O0 0009"),
    ("委托编号", ["600-0009"], "600-0009"),
    ("委托编号", ["600", "?", "0009"], "600 ? 0009"),
    ("委托价格", ["0.3", "500"], "0.3 500"),
    ("委托数量", ["1", "00"], "1 00"),
    ("委托编号", [], ""),
])
def test_numeric_identifier_word_fragments_keep_digits_without_correcting_glyphs(cell_parser, title, fragments, expected):
    result = subprocess.run([str(cell_parser), title, *fragments], capture_output=True, text=True, check=True, timeout=2)
    assert result.stdout.strip() == expected
