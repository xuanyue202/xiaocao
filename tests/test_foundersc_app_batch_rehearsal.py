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
    original_submit = native.submit_prepared_order
    def submit_with_notice(**kwargs):
        receipt = original_submit(**kwargs)
        receipt.payload["action"] = dict(attempted=True, succeeded=True,
            confirm_pressed=True, requires_user_input=False)
        receipt.payload["result_readback"] = dict(kind="submit", status="submit_result_acknowledged",
            broker_order_id=str(6000002 + native.submit_calls), message_matched=True,
            acknowledgment_pressed=True, acknowledgment_mode="semantic_focused_dialog_button")
        return receipt
    native.submit_prepared_order = submit_with_notice
    def run(prices, action="advance", shares=100):
        monkeypatch.setattr(batch.sys, "argv", ["batch", action, "--run-id", "test",
            "--fingerprint", "123******890", "--acknowledge-app-server-simulation",
            "--shares", str(shares), "--prices", *map(str, prices)])
        return batch.main()
    return run, native, directory


@pytest.mark.parametrize("prices", [[.34, .36], [.34, .36, .37], [.34, .36, .37, .38, .39]])
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


@pytest.mark.parametrize("prices", [[.34, .36], [.34, .36, .37], [.34, .36, .37, .38, .39]])
def test_existing_same_symbol_orders_survive_reordered_batch_submit_and_cancel(batch_app, prices):
    run, native, _ = batch_app
    existing_ids = {"6000101", "6000102"}
    for order_id, price in zip(sorted(existing_ids), ("0.3100", "0.3200")):
        row = dict(native.orders[0])
        row.update({
            "证券代码": "512010",
            "证券名称": "既有同代码委托",
            "状态说明": "已报",
            "委托价格": price,
            "委托编号": order_id,
        })
        native.orders.append(row)
    original = native.read_query
    def query(**kwargs):
        if kwargs["kind"] == "today-orders":
            native.orders.reverse()
        return original(**kwargs)
    native.read_query = query

    assert run(prices) == 0

    existing = {row["委托编号"]: row for row in native.orders
                if row["委托编号"] in existing_ids}
    assert set(existing) == existing_ids
    assert {row["状态说明"] for row in existing.values()} == {"已报"}
    assert native.submit_calls == native.cancel_calls == len(prices)


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


@pytest.mark.parametrize("count", [2, 3, 5])
def test_counter_ack_batch_keeps_full_table_reads_out_of_inter_order_path(batch_app, count):
    run, native, _ = batch_app
    trace = []
    query = native.read_query
    submit = native.submit_prepared_order
    def traced_query(**kwargs):
        trace.append(('query', kwargs['kind']))
        return query(**kwargs)
    def confirmed_submit(**kwargs):
        receipt = submit(**kwargs)
        trace.append(('submit', native.submit_calls))
        return receipt
    native.read_query = traced_query
    native.submit_prepared_order = confirmed_submit
    assert run([.34, .36, .37, .38, .39][:count]) == 0
    first = trace.index(('submit', 1))
    last = trace.index(('submit', count))
    assert [entry for entry in trace[first:last] if entry[0] == 'query'] == []


@pytest.mark.parametrize("fault", ["missing_notice", "reused_id", "wrong_account", "unconfirmed"])
def test_notice_fault_stops_remaining_new_writes(batch_app, fault):
    run, native, _ = batch_app
    submit = native.submit_prepared_order
    def faulty_submit(**kwargs):
        receipt = submit(**kwargs)
        if native.submit_calls == 2:
            if fault == "missing_notice":
                receipt.payload.pop("result_readback")
            elif fault == "reused_id":
                receipt.payload["result_readback"]["broker_order_id"] = "6000003"
            elif fault == "wrong_account":
                receipt.payload["trade_account_fingerprint"] = "999******999"
            else:
                receipt.payload["action"]["confirm_pressed"] = False
        return receipt
    native.submit_prepared_order = faulty_submit
    assert run([.34, .36, .37]) == 2
    assert native.submit_calls == 2
    # A replay can only reconcile/clean up these claims; no third submission.
    run([.34, .36, .37])
    assert native.submit_calls == 2


def test_expired_batch_observations_stop_before_second_submit(batch_app, monkeypatch):
    from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter
    original = FounderscNativeAXBrokerAdapter.submit
    def expire_after_first(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if self._submission_batch is not None:
            self._submission_batch["expires"] = 0.0
        return result
    monkeypatch.setattr(FounderscNativeAXBrokerAdapter, "submit", expire_after_first)
    run, native, _ = batch_app
    assert run([.34, .36, .37]) == 2
    assert native.submit_calls == native.cancel_calls == 1


def test_counter_ack_defers_actual_fill_until_exact_trade_readback(batch_app):
    from dataclasses import replace
    from tests.test_foundersc_native_broker import _adapter, _plan
    from xiaocao.live.trading_execution import BrokerStatus
    _, native, _ = batch_app
    adapter = _adapter(native)
    plan = replace(_plan(), code="512010.XSHG", limit_price=.34)
    with adapter.submission_batch([plan]):
        assert adapter.prepare(plan).status == BrokerStatus.PREPARED
        before = list(native.query_calls)
        ack = adapter.submit(plan, "bounded-test-claim")
        assert native.query_calls == before
        assert ack.status == BrokerStatus.ACCEPTED
        assert ack.locator_proof["fill_observation_pending"] is True
        assert ack.filled_shares == 0 and ack.fill_price is None
    native.orders[-1].update(状态说明="已成", 成交数量="100", 成交价格="0.34")
    native.trades = [{"证券代码": "512010", "证券名称": "测试", "成交时间": "103302",
        "买卖标志": "买入", "成交价格": "0.34", "成交数量": "100", "成交金额": "34",
        "成交编号": "9000001", "委托编号": ack.order_id, "股东代码": "A***",
        "成交类型": "成交", "状态说明": "成交"}]
    filled = adapter._reconcile_rows(plan, requested_shares=100, expected_order_id=ack.order_id)
    assert filled.status == BrokerStatus.FILLED
    assert filled.filled_shares == 100 and filled.fill_price == .34
    assert filled.locator_proof["fill_observation_pending"] is False


def test_cached_batch_still_checks_current_account_before_second_order(batch_app):
    run, native, _ = batch_app
    probe = native.probe
    failed = []
    def account_changed(**kwargs):
        receipt = probe(**kwargs)
        if native.submit_calls == 1 and not failed:
            failed.append(True)
            receipt.payload["trade_account_fingerprint"] = "999******999"
        return receipt
    native.probe = account_changed
    assert run([.34, .36, .37]) == 2
    assert failed and native.submit_calls == native.cancel_calls == 1


def test_batch_reservation_and_plan_scope_cannot_be_widened(batch_app):
    from dataclasses import replace
    from tests.test_foundersc_native_broker import _adapter, _plan
    from xiaocao.live.trading_execution import BrokerStatus
    _, native, _ = batch_app
    adapter = _adapter(native)
    plan = replace(_plan(), code="512010.XSHG", limit_price=.34)
    with pytest.raises(ValueError, match="CASH_RESERVATION"):
        with adapter.submission_batch([replace(plan, shares=100000)]):
            pytest.fail("overbudget scope opened")
    with adapter.submission_batch([plan]):
        assert adapter.prepare(plan, requested_shares=200).status == BrokerStatus.REJECTED
        assert adapter.prepare(replace(plan, limit_price=.35)).status == BrokerStatus.REJECTED
    assert native.submit_calls == native.prepare_calls == 0
