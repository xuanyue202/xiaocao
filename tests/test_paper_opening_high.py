"""A real accepting cost seam; clocked quote fixtures are not natural evidence."""
from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos_screen.scripts import paper_record as pr
from xiaocao.live.paper_entry_cost import verified_first_minute_high
from tests.test_paper_kol_integration import runtime, rows  # noqa: F401

REAL_ATTACH = pr._attach_fill_prices

TZ = ZoneInfo("Asia/Shanghai")
DATE = "2026-10-29"
CODE = "688028.XSHG"
NOW = datetime(2026, 10, 29, 9, 32, 5, tzinfo=TZ)


def quote(clock, *, high=94.51, price=91.88, **changes):
    return {"observed_at": f"{DATE}T{clock}+08:00", "raw_quote": {
        "code": CODE, "tradeDate": "20261029", "tradeTimestamp": clock + ":000",
        "open": 93.0, "high": high, "low": 91.2, "trade": price,
        "vol": 2106385, "amt": 195951614.0, **changes}}


def proof():
    return {"source": "xiaocao_api/stock/second_line_detail_info",
            "request": {"codes": CODE}, "observations": [
                quote("09:30:58"), quote("09:32:05")]}


def window():
    # Captured native minute_line shape, including cumulative extrema. These
    # fields alone remain deliberately insufficient to establish HIGH's clock.
    return {"source": "xiaocao_api", "raw_minute_rows": [{
        "code": CODE, "tradeDate": "20261029", "tradeTime": "0931",
        "freq": "1min", "tradeMinutes": 1, "open": 93.0, "high": 94.51,
        "low": 91.2, "close": 91.88, "trade": 91.88,
        "vol": 1567782, "amt": 145861535.0}], "opening_high_proof": proof()}


def validate(data, **changes):
    return verified_first_minute_high(data, code=CODE, trade_date=DATE,
        start_hhmm="0930", end_hhmm="0931", observed_at=changes.get("now", NOW))


def test_equal_clocked_cumulative_highs_prove_first_minute_without_point_max():
    price, evidence = validate(window())
    assert price == 94.51  # both observed last prices are only 91.88
    assert evidence["status"] == "verified"
    assert evidence["source_interval_status"] == "proved_by_cumulative_high_bracket"
    assert evidence["opening_high_proof_sha256"]


@pytest.mark.parametrize("mutation", [
    lambda p: p["observations"].pop(0),
    lambda p: p["observations"][0].update(observed_at=f"{DATE}T09:31:00+08:00"),
    lambda p: p["observations"][0]["raw_quote"].update(tradeTimestamp="09:29:59:000"),
    lambda p: p["observations"][1]["raw_quote"].update(tradeTimestamp="09:30:59:000"),
    lambda p: p["observations"][1]["raw_quote"].update(high=94.52),
    lambda p: p["observations"][1]["raw_quote"].update(high=94.50),
    lambda p: p["observations"][0]["raw_quote"].update(tradeDate="20261028"),
    lambda p: p["observations"][0]["raw_quote"].update(code="000001.XSHE"),
    lambda p: p["observations"][0]["raw_quote"].update(high=float("nan")),
    lambda p: p["observations"][1].update(observed_at=f"{DATE}T09:32:06+08:00"),
    lambda p: p.update(source="public"),
    lambda p: p.update(request={"codes": "000001.XSHE"}),
])
def test_late_missing_changing_wrong_day_or_unbound_quotes_never_prove_cost(mutation):
    data = window()
    mutation(data["opening_high_proof"])
    assert validate(data)[0] is None


def test_auction_only_high_needs_a_real_first_minute_trade_witness():
    data = window()
    data["raw_minute_rows"][0].update(high=93.0)
    for q in data["opening_high_proof"]["observations"]:
        q["raw_quote"].update(high=93.0, trade=93.0)
    assert validate(data)[0] is None  # a cached auction last price is not a trade
    data["opening_high_proof"]["trade_witness_rows"] = [{
        "code": CODE, "tradeDate": "20261029", "tradeTime": "093058",
        "timestamp": 1793237458000, "trade": 93.0, "oneVol": 100, "oneAmt": 9300.0}]
    data["opening_high_proof"]["trade_witness_request"] = {
        "code": CODE, "codeType": 0, "isLess": 0, "count": 5000}
    data["opening_high_proof"]["trade_witness_observed_at"] = NOW.isoformat()
    assert validate(data)[0] == 93.0
    data["opening_high_proof"]["trade_witness_rows"][0]["tradeTime"] = "093100"
    assert validate(data)[0] is None


def test_actual_attach_path_accepts_high_without_relaxing_eligibility():
    class Client:
        def minute_line(self, *args, **kwargs):
            return copy.deepcopy(window()["raw_minute_rows"])
    picks = [{"code": CODE, "open": 93.0, "basket_price": 94.3392}]
    bought, skipped = pr._attach_fill_prices(Client(), picks, DATE,
        start_hhmm="0930", end_hhmm="0931", limit_premium_pct=0.5,
        conservative_entry=True, opening_high_proofs={CODE: proof()})
    assert not skipped and bought[0]["_paper_fill"]["price"] == 94.51
    # Adverse cost exceeds limit and basket; legacy T remains at its own price.
    legacy, _ = pr._attach_fill_prices(Client(), picks, DATE,
        start_hhmm="0930", end_hhmm="0931", limit_premium_pct=0.5)
    assert legacy[0]["_paper_fill"]["price"] < 94.51
    bought, skipped = REAL_ATTACH(Client(), [{**picks[0], "basket_price": 80}], DATE,
        start_hhmm="0930", end_hhmm="0931", limit_premium_pct=0.5,
        conservative_entry=True, opening_high_proofs={CODE: proof()})
    assert not bought and skipped[0]["_paper_fill"]["skip_reason"] == "LIMIT_NOT_REACHED"


def test_capture_is_bounded_and_retains_actual_pre_and_post_read_clocks():
    from xiaocao.live.paper_opening_high import capture_opening_high
    times = [datetime(2026, 10, 29, 9, 30, 56, tzinfo=TZ)]
    class Client:
        def second_line_detail_info(self, codes):
            assert codes == CODE
            clock = times[0].strftime("%H:%M:%S")
            return {CODE: quote(clock)["raw_quote"]}
    def sleep(seconds):
        assert 0 < seconds <= 2
        times[0] += timedelta(seconds=seconds)
    result = capture_opening_high(Client(), [CODE], DATE,
        now=lambda: times[0], sleep=sleep)
    observations = result[CODE]["observations"]
    assert any(q["observed_at"] < f"{DATE}T09:31:00+08:00" for q in observations)
    assert times[0] == NOW.replace(minute=31, second=0)
    data = window()
    data["opening_high_proof"] = result[CODE]
    assert validate(data)[0] == 94.51


def test_late_capture_does_not_reconstruct_or_query_completed_first_minute():
    from xiaocao.live.paper_opening_high import capture_opening_high
    result = capture_opening_high(object(), [CODE], DATE, now=lambda: NOW,
        sleep=lambda _: pytest.fail("late capture must not wait"))
    assert result[CODE]["errors"] == ["FIRST_MINUTE_PRE_CAPTURE_MISSED"]
    assert result[CODE]["observations"] == []


def test_immediate_post_boundary_proof_survives_later_daily_high_increases():
    data = window()
    data["opening_high_proof"]["observations"][1] = quote("09:31:02")
    assert validate(data)[0] == 94.51
    assert validate(data, now=NOW.replace(second=4))[0] is None


def test_auth_failure_is_explicit_and_raw_rejection_proof_is_retained():
    data = window()
    data["opening_high_proof"]["errors"] = ["API_AUTHENTICATION_FAILED_990502"]
    price, evidence = validate(data)
    assert price is None
    assert evidence["reason"] == "FIRST_MINUTE_API_AUTHENTICATION_FAILED_990502"
    assert evidence["opening_high_proof"] == data["opening_high_proof"]


def test_native_trade_witness_authentication_failure_remains_auth_failure():
    from xiaocao.api.errors import ApiAuthError
    from xiaocao.live.paper_opening_high import capture_opening_high
    clock = [NOW.replace(minute=30, second=58)]
    class Client:
        def second_line_detail_info(self, codes):
            return {CODE: quote(clock[0].strftime("%H:%M:%S"), high=93.0)["raw_quote"]}
        def post(self, path, request):
            assert path == "/stock/each_trade"
            raise ApiAuthError("API returned code=990502")
    def sleep(seconds):
        clock[0] += timedelta(seconds=seconds)
    captured = capture_opening_high(Client(), [CODE], DATE, now=lambda: clock[0], sleep=sleep)
    data = window()
    data["raw_minute_rows"][0]["high"] = 93.0
    data["opening_high_proof"] = captured[CODE]
    assert validate(data)[1]["reason"] == "FIRST_MINUTE_API_AUTHENTICATION_FAILED_990502"


@pytest.mark.parametrize("fault", [None, "changed_freeze", "corrupt_capture", "missing_pre", "partial_pre"])
def test_original_canonical_writer_capture_locking_pairing_and_terminal_faults(runtime, monkeypatch, fault):
    from xiaocao.live import morning_bundle, paper_opening_high
    from xiaocao.live import paper_decision_support as support
    root, live, writer, run = runtime
    candidates = rows(live / "signal_snapshots.jsonl")
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-morning")
    monkeypatch.setenv("CODEX_THREAD_ID", "producer")
    morning_bundle.publish_captured_batch(live, "2026-09-06",
        snapshot="".join(json.dumps(r) + "\n" for r in candidates if r["book"] == "B").encode(),
        strategy_sha="a" * 40, source_readiness={"completeness": "observed_responses"}, timing={})
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-morning-execution")
    monkeypatch.setenv("CODEX_THREAD_ID", "original-consumer")
    monkeypatch.setenv("XIAOCAO_DAILY_RUN_DIR", str(root / "original-run"))
    locked = []
    original_lock = writer.accounts.ledger_lock
    @contextmanager
    def tracking_lock(path):
        with original_lock(path):
            locked.append(path)
            try:
                yield
            finally:
                locked.pop()
    monkeypatch.setattr(writer.accounts, "ledger_lock", tracking_lock)
    captures = []
    def captured(_client, codes, date):
        assert not locked  # includes all timed reads, not a second writer
        captures.append(codes)
        result = {}
        for code in codes:
            item = proof()
            item["request"] = {"codes": ",".join(codes)}
            for q in item["observations"]:
                q["observed_at"] = q["observed_at"].replace(DATE, date)
                q["raw_quote"].update(code=code, tradeDate="20260906", open=10.0,
                                       high=10.2, low=9.98, trade=10.05)
            if fault == "missing_pre" or (fault == "partial_pre" and code == "000001.XSHE"):
                item["observations"].pop(0)
            result[code] = item
        return result
    monkeypatch.setattr(paper_opening_high, "capture_opening_high", captured)
    class Client:
        def minute_line(self, code, *args, **kwargs):
            return [{**window()["raw_minute_rows"][0], "code": code,
                "tradeDate": "20260906", "open": 10.0, "high": 10.2,
                "low": 9.98, "close": 10.05, "trade": 10.05, "amt": 1000, "vol": 100}]
    monkeypatch.setattr(writer, "XiaocaoClient", lambda **kwargs: Client())
    monkeypatch.setattr(writer, "_attach_fill_prices", REAL_ATTACH)
    parse = writer._parse_args
    def arguments():
        args = parse()
        args.no_wait_fill_window = False
        args.allow_legacy_snapshots = False
        return args
    monkeypatch.setattr(writer, "_parse_args", arguments)
    def settled(*args):
        assert not locked
        if fault == "corrupt_capture":
            path = root / "original-run/paper-opening-high-2026-09-06.json"
            data = json.loads(path.read_text())
            data["proofs"] = {}
            path.write_text(json.dumps(data))
    monkeypatch.setattr(writer, "_wait_until_fill_window_complete", settled)
    if fault == "changed_freeze":
        original_prepare = writer._prepare_opening_high
        def changed(args):
            original_prepare(args)
            args._opening_high_snapshot_sha256 = "0" * 64
        monkeypatch.setattr(writer, "_prepare_opening_high", changed)
    before = (live / "paper_account.json").read_bytes()
    if fault in {"changed_freeze", "corrupt_capture"}:
        with pytest.raises(ValueError, match="FIRST_MINUTE_(PROOF_BATCH|CAPTURE_HASH)_MISMATCH"):
            run()
        assert (live / "paper_account.json").read_bytes() == before
        assert support.read_consumption(root, "2026-09-06", "mode_exec_star") is None
        return
    if fault in {"missing_pre", "partial_pre"}:
        with pytest.raises(RuntimeError, match="FIRST_MINUTE_SOURCE_BLOCKED"):
            run()
        terminal = support.read_consumption_result(root, "2026-09-06", "mode_exec_star")
        assert terminal["status"] == ("source_blocked" if fault == "missing_pre" else "bought_source_blocked")
        assert terminal["buy_count"] == (0 if fault == "missing_pre" else 3)
        assert terminal["entry_source_failures"]
        before = (live / "paper_account.json").read_bytes()
    else:
        positions, claim, terminal = run()
        assert terminal["status"] == "bought" and terminal["buy_count"] == 3
        a, b = [[r for r in positions if r["book"] == book] for book in ("A", "B")]
        assert [(r["code"], r["shares"], r["entry_price"]) for r in a] == [
            (r["code"], r["shares"], r["entry_price"]) for r in b]
        assert all(r["entry_price"] == 10.2 and r["fill_cost_evidence"]["status"] == "verified" for r in b)
        assert sum(r["entry_cash_out"] for r in b) <= 50000
        before = (live / "paper_account.json").read_bytes()
    # A duplicate must preserve both no-replay and the original failure status.
    if fault in {"missing_pre", "partial_pre"}:
        with pytest.raises(RuntimeError, match="FIRST_MINUTE_SOURCE_BLOCKED"):
            run()
    else:
        run()
    assert len(captures) == 1 and (live / "paper_account.json").read_bytes() == before
