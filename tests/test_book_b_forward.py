from copy import deepcopy
from datetime import datetime, timedelta
import json
import importlib.util
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from xiaocao.live.book_b_capital import digest
from xiaocao.live.book_b_workflow import compare_final_plans
from xiaocao.live.trading_runner import frozen_rows_digest
from xiaocao.research.book_b_forward import PROTOCOL, _read_state, performance, transact

pytestmark = pytest.mark.app_simulation
NOW = datetime(2026,10,22,9,35,tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.fixture(autouse=True)
def script_import_path(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/"scripts"))


@pytest.mark.parametrize("fault", [None, "code", "date", "missing", "clock"])
def test_acquisition_requires_raw_symbol_date_and_complete_window(fault):
    spec = importlib.util.spec_from_file_location("forward_cli", Path(__file__).resolve().parents[1]/"scripts/research_book_b_forward.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    start = NOW.replace(minute=36)
    end = start+timedelta(minutes=4)
    rows = [{"code":"000001.XSHE","tradeDate":"20261022","tradeTime":(start+timedelta(minutes=i)).strftime("%H%M"),
             "trade":10.,"vol":10000.,"amt":100000.} for i in range(5)]
    if fault == "code": rows[0]["code"] = "600519.XSHG"
    if fault == "date": rows[0]["tradeDate"] = "20261021"
    if fault == "missing": rows[0].pop("tradeDate")
    if fault == "clock": rows[0]["tradeTime"] = "9960"
    class Client:
        def minute_line(self, *args, **kwargs): return rows
    result = cli.window_evidence(Client(), {"code":"000001.XSHE", "window_start":start.isoformat(),
        "window_end":end.isoformat()}, NOW+timedelta(minutes=7))
    assert result["complete"] is (fault is None)


def inputs(now=NOW):
    rows = [{"date":now.date().isoformat(),"book":"B","is_live":True,"code":"000001.XSHE",
        "name":"test","mode":"m1","mode_state":"ACTIVE","mode_exec_star":True,
        "mode_trade_eligible":True,"mode_star":True,"mode_exec_score":10,"open":10.,"basket_price":11.,
        "mode_exec_target_weight":.5,"executable_fillable":True}]
    return {"rows":rows,"freeze":{"market_date":now.date().isoformat(),"strategy_run_id":"original",
        "strategy_sha":"a"*40,"snapshot_sha256":frozen_rows_digest(rows),"snapshot_raw_sha256":"b"*64,
        "snapshot_row_count":1,"checkpoint_sha256":"c"*64},
        "policy":{"status":"neutral","book":"B","runtime":"live","reason":"baseline"},
        "performance_factor":1.,"marks":{},"market_guards":{"000001.XSHE":{"allowed":True,"observed_at":now.isoformat()}}}


def order_windows(state, now, *, cross=True):
    windows={}
    for account in state["accounts"].values():
        for order in account["orders"]:
            start=datetime.fromisoformat(order["window_start"])
            windows[order["order_id"]]={"code":order["code"],"window_start":order["window_start"],
                "window_end":order["window_end"],"complete":True,"observed_at":now.isoformat(),
                "bars":[{"at":(start+timedelta(minutes=i)).isoformat(),"price":10. if cross else 20.,
                         "volume_shares":100000.} for i in range(5)]}
    return windows


def test_funded_four_controls_resolve_only_future_bound_windows_and_do_not_replay(tmp_path):
    first=transact(tmp_path,phase="morning",inputs=inputs(),now=NOW)
    state=_read_state(tmp_path/"state.json")
    assert len(state["accounts"])==4
    for account in state["accounts"].values():
        assert len(account["orders"])==1
        order=account["orders"][0]
        assert datetime.fromisoformat(order["window_start"])>NOW
        assert order["shares"] % 100 == 0 and order["reserved_cents"]<=5000000
    assert state["accounts"]["open_limit"]["orders"][0]["limit_price"]==10.
    again=transact(tmp_path,phase="morning",inputs=inputs(),now=NOW+timedelta(minutes=1))
    assert again["status"]=="already_consumed"
    assert all(len(a["orders"])==1 for a in _read_state(tmp_path/"state.json")["accounts"].values())
    later=NOW+timedelta(minutes=7)
    observation={"windows":order_windows(state,later),"statuses":{},"marks":{"000001.XSHE":{
        "price":11.,"status":"ok","observed_at":later.isoformat()}}}
    transact(tmp_path,phase="monitor",inputs=observation,now=later)
    after=_read_state(tmp_path/"state.json")
    for account in after["accounts"].values():
        assert account["orders"][0]["status"]=="filled"
        assert account["cash_cents"]>=0 and account["lots"][0]["shares"]>0
    cash={k:v["cash_cents"] for k,v in after["accounts"].items()}
    transact(tmp_path,phase="monitor",inputs=observation,now=later)
    assert cash=={k:v["cash_cents"] for k,v in _read_state(tmp_path/"state.json")["accounts"].items()}
    report=performance(tmp_path)
    assert report["accounts"]["app_b_control"]["net_model_return_pct"]>0
    assert report["accounts"]["app_b_control"]["app_realized_profit"] is None


def test_unknown_fill_reserves_cash_and_never_mints_nav(tmp_path):
    transact(tmp_path,phase="morning",inputs=inputs(),now=NOW)
    transact(tmp_path,phase="monitor",inputs={"windows":{},"statuses":{},"marks":{}},now=NOW+timedelta(minutes=7))
    state=_read_state(tmp_path/"state.json")
    assert all(a["orders"][0]["status"]=="unknown" and not a["lots"] for a in state["accounts"].values())
    report=performance(tmp_path)
    assert all(a["reserved_cash"]>0 and a["marked_nav"] is None for a in report["accounts"].values())
    later = NOW + timedelta(minutes=9)
    exact = order_windows(state, later)
    for window in exact.values():
        for bar in window["bars"]:
            bar["volume_shares"] = 10000.  # Only 500 shares of proved model capacity.
    transact(tmp_path,phase="monitor",inputs={"windows":exact,"marks":{}},now=later)
    after = _read_state(tmp_path/"state.json")
    assert all(a["orders"][0]["status"]=="partial_expired" and
               a["orders"][0]["filled_shares"]==500 for a in after["accounts"].values())
    assert all(a["marked_nav"] is None for a in performance(tmp_path)["accounts"].values())


def test_cold_and_late_inputs_record_denominator_without_model_orders(tmp_path):
    data=inputs()
    data["rows"][0].update(mode_state="COLD",mode_trade_eligible=False,mode_exec_star=False)
    data["freeze"]["snapshot_sha256"]=frozen_rows_digest(data["rows"])
    transact(tmp_path,phase="morning",inputs=data,now=NOW)
    assert not any(a["orders"] for a in _read_state(tmp_path/"state.json")["accounts"].values())
    root=tmp_path/"late"
    transact(root,phase="morning",inputs=inputs(),now=NOW.replace(hour=15))
    state=_read_state(root/"state.json")
    assert state["morning_dates"]==["2026-10-22"]
    assert not any(a["orders"] for a in state["accounts"].values())


def test_atomic_conflicting_window_preserves_prior_funded_state(tmp_path):
    transact(tmp_path,phase="morning",inputs=inputs(),now=NOW)
    before=(tmp_path/"state.json").read_bytes()
    later=NOW+timedelta(minutes=7)
    windows=order_windows(_read_state(tmp_path/"state.json"),later)
    next(iter(windows.values()))["code"]="wrong"
    with pytest.raises(ValueError,match="BINDING"):
        transact(tmp_path,phase="monitor",inputs={"marks":{},"windows":windows},now=later)
    assert (tmp_path/"state.json").read_bytes()==before


def test_report_joins_real_app_plan_and_keeps_pending_and_missing_dates(tmp_path):
    root = tmp_path/"output/research/app_b_forward"
    data = inputs()
    data["trading_dates"] = ["2026-10-22"]
    transact(root,phase="morning",inputs=data,now=NOW)
    state = _read_state(root/"state.json")
    final = deepcopy(state["events"][0]["result"]["variants"]["app_b_control"]["final_plan"])
    final["allocation"]["available_cash"] = 200000
    final["receipt_sha256"] = digest({k:v for k,v in final.items() if k != "receipt_sha256"})
    history = tmp_path/"output/live/book_b_live_execution/runs/history"
    history.mkdir(parents=True)
    (history/"2026-10-22-original.json").write_text(json.dumps({"run_id":"2026-10-22-original",
        "trade_date":"2026-10-22","runner_identity":{"automation_id":"xiaocao-book-b-live-morning"},"final_plan":final}))
    spec = importlib.util.spec_from_file_location("forward_report_cli", Path(__file__).resolve().parents[1]/"scripts/research_book_b_forward.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.write_reports(tmp_path,NOW)
    report = json.loads((root/"performance.json").read_text())
    assert report["app_plan_comparisons"][0]["first_divergence"] == "account_allocation"
    assert all(a["pending_orders"]==1 and a["unknown_orders"]==0 for a in report["accounts"].values())
    transact(root,phase="eod",inputs={"windows":{},"marks":{},"trading_dates":["2026-10-22","2026-10-23"]},
             now=NOW.replace(day=23,hour=15))
    assert performance(root)["missing_morning_dates"] == ["2026-10-23"]


def test_sell_lot_cash_fee_and_t1_close_model_cycle(tmp_path):
    transact(tmp_path,phase="morning",inputs=inputs(),now=NOW)
    later=NOW+timedelta(minutes=7)
    transact(tmp_path,phase="monitor",inputs={"windows":order_windows(_read_state(tmp_path/"state.json"),later),
        "marks":{"000001.XSHE":{"price":10.,"status":"ok","observed_at":later.isoformat()}}},now=later)
    def closing(day):
        now=NOW.replace(day=day,hour=14,minute=45)
        state=_read_state(tmp_path/"state.json")
        statuses={v:{lot["lot_id"]:{"triggered":True,"sell_reason":"EOD_DISCIPLINE_1455",
            "market_guard_status":"ok","market_guard_observed_at":now.isoformat(),
            "latest_price":11.,"market_guard_down_price":9.} for lot in a["lots"]} for v,a in state["accounts"].items()}
        transact(tmp_path,phase="monitor",inputs={"statuses":statuses,"marks":{"000001.XSHE":{
            "price":11.,"status":"ok","observed_at":now.isoformat()}}},now=now)
        return now
    closing(22)
    assert all(len(a["orders"])==1 for a in _read_state(tmp_path/"state.json")["accounts"].values())
    now=closing(23)
    state=_read_state(tmp_path/"state.json")
    assert all(len(a["orders"])==2 for a in state["accounts"].values())
    later=now+timedelta(minutes=7)
    windows=order_windows(state,later)
    for account in state["accounts"].values():
        order=account["orders"][-1]
        for bar in windows[order["order_id"]]["bars"]:
            bar["price"]=11.
    transact(tmp_path,phase="monitor",inputs={"windows":windows,"marks":{}},now=later)
    state=_read_state(tmp_path/"state.json")
    for account in state["accounts"].values():
        sell=account["orders"][-1]
        assert sell["status"]=="filled" and account["lots"][0]["shares"]==0
        assert account["cash_cents"]==PROTOCOL["initial_capital_cents"]+sell["realized_pnl_cents"]
