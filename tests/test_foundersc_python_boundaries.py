"""Process, build and credential failures at the Python/native boundary."""
import json
import subprocess

import pytest

from tests.test_foundersc_native_ax import HelperRunner, _helper, _receipt
from xiaocao.live import foundersc_native_ax as ax
from xiaocao.live.capital_keychain import KeychainCapitalRuntime, CapitalRuntimeUnavailable
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight


@pytest.mark.parametrize("field,value", [
    ("quantity", 100.5), ("quantity", True), ("quantity", 0), ("quantity", -100),
    ("quantity", float("inf")), ("quantity", "100x"),
    ("price", float("nan")), ("price", float("inf")), ("price", 0),
    ("price", -1), ("price", True), ("price", 1.1234567),
    ("code", "000001.BAD"), ("code", "00001"), ("side", "purchase"),
    ("expected_fingerprint", ""),
])
@pytest.mark.parametrize("method", ["prepare_order", "submit_prepared_order"])
def test_invalid_order_input_never_starts_helper(tmp_path, field, value, method):
    runner = HelperRunner(_receipt())
    client = ax.FounderscNativeAXClient(helper_path=_helper(tmp_path), runner=runner)
    args = dict(code="000001.XSHE", side="BUY", price=10.0, quantity=100,
                expected_fingerprint="123******890")
    args[field] = value
    if method == "submit_prepared_order":
        args["explicitly_enabled"] = True
    with pytest.raises(ax.FounderscNativeAXError, match="NATIVE_AX_ORDER"):
        getattr(client, method)(**args)
    assert runner.calls == []


@pytest.mark.parametrize("raw,reason", [
    (b"", "EMPTY_RECEIPT"), (b"\xff", "INVALID_RECEIPT"),
    (b"{}\n{}", "INVALID_RECEIPT"), (b"[]", "RECEIPT_SHAPE"),
    (_receipt(helper_version=None), "HELPER_VERSION_MISSING"),
    (_receipt(helper_version=True), "HELPER_VERSION_MISSING"),
    (_receipt(status=None), "STATUS_MISSING"),
    (_receipt(nested=[{"api_token": "private"}]), "CONTAINS_SENSITIVE_KEY"),
])
def test_malformed_process_receipt_is_never_success(tmp_path, raw, reason):
    client = ax.FounderscNativeAXClient(helper_path=_helper(tmp_path), runner=HelperRunner(raw))
    with pytest.raises(ax.FounderscNativeAXError, match=reason):
        client.probe()


@pytest.mark.parametrize("failure,reason", [
    ("timeout", "COMMAND_TIMEOUT"), ("os", "COMMAND_START_FAILED"),
    ("exit", "COMMAND_FAILED"), ("missing", "HELPER_MISSING"),
])
def test_process_failure_does_not_retry(tmp_path, failure, reason):
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 1, output=b"private")
        if failure == "os":
            raise OSError("private")
        return subprocess.CompletedProcess(command, 1, stdout=_receipt(), stderr=b"private")
    helper = _helper(tmp_path)
    if failure == "missing":
        helper.unlink()
    client = ax.FounderscNativeAXClient(helper_path=helper, runner=runner)
    with pytest.raises(ax.FounderscNativeAXError, match=reason) as caught:
        client.version()
    assert "private" not in str(caught.value)
    assert len(calls) == (0 if failure == "missing" else 1)


@pytest.fixture
def source_tree(tmp_path, monkeypatch):
    package = tmp_path / ax.PACKAGE_RELATIVE_PATH
    (package / "Sources").mkdir(parents=True)
    (package / "Package.swift").write_text("// package")
    (package / "Sources/main.swift").write_text("// source")
    monkeypatch.setattr(ax.shutil, "which", lambda _: "/test/swift")
    return tmp_path


@pytest.mark.parametrize("failure,reason", [
    ("toolchain", "SWIFT_TOOLCHAIN_MISSING"), ("timeout", "BUILD_TIMEOUT"),
    ("os", "BUILD_START_FAILED"), ("exit", "BUILD_FAILED"),
    ("locate-timeout", "BIN_PATH_FAILED"), ("locate-exit", "BIN_PATH_FAILED"),
    ("artifact", "BUILD_ARTIFACT_MISSING"),
])
def test_build_failures_never_install_a_helper(source_tree, monkeypatch, failure, reason):
    if failure == "toolchain":
        monkeypatch.setattr(ax.shutil, "which", lambda _: None)
    def runner(command, **kwargs):
        locating = "--show-bin-path" in command
        if failure == "timeout" or (locating and failure == "locate-timeout"):
            raise subprocess.TimeoutExpired(command, 1)
        if failure == "os":
            raise OSError()
        failed = failure == "exit" or (locating and failure == "locate-exit")
        return subprocess.CompletedProcess(command, int(failed), stdout=str(source_tree / "missing"))
    with pytest.raises(ax.FounderscNativeAXError, match=reason):
        ax.build_helper(root=source_tree, runner=runner)
    assert not ax.expected_helper_path(source_tree).exists()


def test_build_cache_tracks_source_and_executable_install(source_tree):
    binary = source_tree / ax.HELPER_NAME
    binary.write_bytes(b"compiled-test-fixture")
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=str(source_tree).encode())
    first = ax.build_helper(root=source_tree, runner=runner)
    assert first["status"] == "built" and len(calls) == 2
    assert ax.build_helper(root=source_tree, runner=runner)["status"] == "reused"
    assert len(calls) == 2
    (source_tree / ax.PACKAGE_RELATIVE_PATH / "Sources/main.swift").write_text("// changed")
    second = ax.build_helper(root=source_tree, runner=runner)
    assert second["helper_path"] != first["helper_path"] and len(calls) == 4


@pytest.mark.parametrize("stage", ["metadata", "secret"])
@pytest.mark.parametrize("failure", ["timeout", "os", "denied", "invalid-utf8", "empty"])
def test_keychain_failures_remain_local_and_credential_free(tmp_path, stage, failure):
    def runner(command, **kwargs):
        if ("-w" in command) == (stage == "secret"):
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 1, output=b"private")
            if failure == "os":
                raise OSError("private")
            return subprocess.CompletedProcess(command, 1 if failure == "denied" else 0,
                stdout=b"\xff" if failure == "invalid-utf8" else b"", stderr=b"")
        return subprocess.CompletedProcess(command, 0,
            stdout=b"true\n" if "-w" in command else b'"acct"<blob>="1234567890"', stderr=b"")
    runtime = KeychainCapitalRuntime(runner=runner)
    report = runtime.preflight(auth_path=tmp_path / "absent.json")
    assert report["authorization_valid"] is False
    if stage == "secret" or failure in {"timeout", "os", "denied"}:
        with pytest.raises(CapitalRuntimeUnavailable):
            runtime.safety_env()
    trade = FounderscKeychainPreflight(runner=runner).run(read_secrets=True)
    assert "private" not in json.dumps(trade) + json.dumps(report)
    assert "1234567890" not in json.dumps(trade)
