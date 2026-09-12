"""Exercise the batch CLI through real Python broker/execution/store code."""
import json

import pytest

from scripts import foundersc_app_batch_rehearsal as batch
from scripts import foundersc_app_rehearsal as single
from tests.test_foundersc_app_rehearsal import app


@pytest.fixture
def batch_app(app, monkeypatch):
    _, native, directory = app
    monkeypatch.setattr(batch, "ROOT", single.ROOT)
    monkeypatch.setattr(batch, "FounderscNativeAXClient", lambda: native)
    monkeypatch.setattr(batch, "source_digest", lambda: "test-source")
    native.command_timings = []
    def run(prices, action="advance", shares=100):
        monkeypatch.setattr(batch.sys, "argv", ["batch", action, "--run-id", "test",
            "--fingerprint", "123******890", "--acknowledge-app-server-simulation",
            "--shares", str(shares), "--prices", *map(str, prices)])
        return batch.main()
    return run, native, directory


@pytest.mark.parametrize("prices", [[.34, .36], [.34, .36, .37, .38, .39]])
def test_cli_multiple_outstanding_then_exact_cancel_and_idempotent_replay(batch_app, prices):
    run, native, directory = batch_app
    def snapshot_seen():
        return [dict(row) for row in native.orders]
    observed = []
    original = native.read_query
    def query(**kwargs):
        if kwargs["kind"] == "today-orders":
            observed.append(snapshot_seen())
        # Native order-list position is unstable; IDs remain authoritative.
        native.orders.reverse()
        return original(**kwargs)
    native.read_query = query
    assert run(prices) == 0
    assert any(sum(row["状态说明"] == "未报" for row in rows) == len(prices) + 1
               for rows in observed)
    assert native.submit_calls == native.cancel_calls == len(prices)
    assert run(prices) == 0
    assert run(prices, "cleanup") == 0
    assert native.submit_calls == native.cancel_calls == len(prices)
    assert next(row for row in native.orders if row["委托编号"] == "6000002")["状态说明"] == "未报"
    assert not (directory / "ownership.jsonl").exists()


def test_kth_lost_response_seals_batch_and_cleans_known_claims(batch_app):
    run, native, directory = batch_app
    original = native.submit_prepared_order
    def submit(**kwargs):
        result = original(**kwargs)
        if native.submit_calls == 2:
            raise TimeoutError("service accepted but response was lost")
        return result
    native.submit_prepared_order = submit
    prices = [.34, .36, .37, .38, .39]
    assert run(prices) == 2
    assert native.submit_calls == native.cancel_calls == 2
    assert (directory / "cleanup-started.json").exists()
    assert run(prices) == 2
    assert native.submit_calls == native.cancel_calls == 2
    assert sum(row["状态说明"] == "未报" for row in native.orders) == 1  # unrelated order


def test_manifest_tampering_and_aggregate_budget_make_zero_new_orders(batch_app):
    run, native, directory = batch_app
    with pytest.raises(ValueError, match="BUDGET"):
        run([9.9, 9.8])
    assert native.submit_calls == 0
    assert run([.34, .36]) == 0
    path = directory / "batch.json"
    payload = json.loads(path.read_text())
    payload["baseline"]["broker_summary"]["available_cash"] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="IMMUTABLE"):
        run([.34, .36])
    assert native.submit_calls == native.cancel_calls == 2


@pytest.mark.parametrize("shares", [200,300,400])
def test_batch_quantity_switches_are_preserved(batch_app, shares):
    run, native, directory = batch_app
    assert run([.34,.35,.36,.37,.38], shares=shares) == 0
    assert all(int(row["委托数量"]) == shares for row in native.orders if row["委托编号"] != "6000002")
    assert native.submit_calls == native.cancel_calls == 5
