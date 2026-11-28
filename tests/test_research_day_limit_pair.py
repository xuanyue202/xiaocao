import datetime as dt
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_day_limit_pair as pair
from xiaocao.research.weekly_evidence import DAY_PAIR, observe_day_pair

DAY, NEXT, CLOSED = "2026-11-30", "2026-12-01", "2026-11-27"
CODE = "603960.XSHG"
CAND = dict(code=CODE, up=12, down=8, limit=10, plan_id="p", plan_hash="a" * 64)
MORNING = {"status": "eligible", "candidate": CAND, "day": DAY}
REG = {"registered_at": "2026-11-28T16:00:00+08:00", "protocol": pair.PROTOCOL}


def prices(cheap):
    return {
        t: {"trade": 9.8 if t == cheap else 10.5, "vol": 100000} for t in pair.MINUTES
    }


def test_resting_order_later_cross_and_missing_path():
    a = pair.initial_accounts()
    points = prices("0955")
    for start in pair.STARTS:
        event = pair.day_fill(a[start + "/normal"], CAND, points, start, "normal", DAY)
        assert event["fill_minute"] == "0955" and event["shares"] == 100
    assert a["0931/normal"] == a["0946/normal"]
    points.pop("0940")
    with pytest.raises(ValueError, match="incomplete_DAY"):
        pair.day_fill(a["0946/normal"], CAND, points, "0946", "normal", DAY)


def test_overlap_t1_hash_bound_weekly_and_missing_session(tmp_path, monkeypatch):
    root = tmp_path / "day_limit_pair"
    root.mkdir()
    monkeypatch.setattr(pair, "source_points", lambda *args: prices("0935"))
    monkeypatch.setattr(
        pair, "close_guard", lambda *args: {"down": 8, "bid_shares": 1e5}
    )

    def sealed(day):
        m = dict(
            MORNING,
            day=day,
            observed_at=pair.at(day, "0930").isoformat(),
            registration_sha256=pair.sha(pair.encode(REG)),
        )
        m["receipt_sha256"] = pair.sha(pair.encode(m))
        return m

    first = pair.close_session(root, tmp_path, DAY, [DAY], REG, sealed(DAY), None)
    assert (
        first["accounts"]["0931/normal"]["lots"]
        and not first["accounts"]["0946/normal"]["lots"]
    )
    assert first["effects"]["0946/normal"]["entry"]["status"] == "expired_unfilled"
    p = root / (DAY + ".close.json")
    p.write_bytes(pair.encode(first))
    second = pair.close_session(
        root, tmp_path, NEXT, [DAY, NEXT], REG, sealed(NEXT), None
    )
    assert all(not a["lots"] for a in second["accounts"].values())
    assert second["effects"]["0946/normal"]["entry"]["status"] == "prior_slot_occupied"
    q = root / (NEXT + ".close.json")
    q.write_bytes(pair.encode(second))
    contents = {
        DAY_PAIR + "registration.json": pair.encode(REG),
        DAY_PAIR + p.name: p.read_bytes(),
        DAY_PAIR + DAY + ".morning.json": pair.encode(sealed(DAY)),
        DAY_PAIR + NEXT + ".morning.json": pair.encode(sealed(NEXT)),
        DAY_PAIR + q.name: q.read_bytes(),
    }
    v = observe_day_pair(contents, dt.date.fromisoformat(NEXT))
    assert v["opportunities"] == 1 and v["difference_yuan"]["normal"] < 0
    contents[DAY_PAIR + p.name] += b" "
    assert (
        observe_day_pair(contents, dt.date.fromisoformat(NEXT))["status"] == "invalid"
    )
    missing = pair.close_session(
        root,
        tmp_path,
        "2026-12-03",
        [DAY, NEXT, "2026-12-02", "2026-12-03"],
        REG,
        {"status": "gap", "reason": "no_seal"},
        None,
    )
    assert missing["historical_gaps"] == ["2026-12-02", "2026-12-03"]


def test_natural_cutoff_does_not_create_early_evidence_on_late_retry(tmp_path):
    stamp = pair.at(DAY, "0940")
    pair.register(tmp_path, pair.at(CLOSED, "1500"))
    run = lambda: pair.run(
        tmp_path,
        tmp_path,
        DAY,
        [CLOSED, DAY],
        True,
        "unused",
        clock=lambda: stamp,
        sleep=lambda _: None,
    )
    initial = run()
    again = run()
    assert initial == again and initial["status"] == "gap"
    assert (
        json.loads(Path(initial["receipt"]).read_bytes())["reason"]
        == "pre0931_seal_missed"
    )


def test_invalid_retained_receipts_never_fund_a_new_day(tmp_path):
    record = dict(
        day=DAY,
        registration_sha256=pair.sha(pair.encode(REG)),
        status="gap",
        reason="missed",
        observed_at=pair.at(DAY, "0932").isoformat(),
    )
    record["receipt_sha256"] = pair.sha(pair.encode(record))
    assert pair.validated_morning(record, DAY, REG)["status"] == "gap"
    with pytest.raises(ValueError):
        pair.validated_morning(record, NEXT, REG)
    pair.register(tmp_path, pair.at(CLOSED, "1600"))
    folder = tmp_path / "day_limit_pair"
    (folder / (DAY + ".close.json")).write_text(
        json.dumps({"day": NEXT, "accounts": {}})
    )
    with pytest.raises(ValueError):
        pair.prior_account(folder, NEXT, REG)


def test_stale_week_blocks_reported_net_and_split_drawdown_pauses():
    first = pair.close_session(
        Path("/not-an-account-path"),
        Path("/not-an-account-path"),
        DAY,
        [DAY],
        REG,
        {"status": "gap", "reason": "missed"},
        None,
    )
    view = observe_day_pair(
        {
            DAY_PAIR + "registration.json": pair.encode(REG),
            DAY_PAIR + DAY + ".close.json": pair.encode(first),
        },
        dt.date.fromisoformat(NEXT),
    )
    assert not view["current"] and view["difference_yuan"]["stress"] is None
    risk = pair.split_risk(
        {"a": {"actual": {"status": "closed", "actual_realized_net": -286.09}}},
        {},
        None,
    )
    assert risk["paused"] and risk["nav_yuan"] == 2713.91


def test_sealed_leader_walks_down_fixed_live_order_with_no_close_inputs():
    from research_relay_walkdown import choose

    rows = [
        dict(code=c, codeName="股票", isPreSt=0, jsjl=20, xcjw=350)
        for c in ("000001.XSHE", "000002.XSHE", "000003.XSHE")
    ]
    points = {
        r["code"]: dict(open=10, trade=price, up=11, down=9, vol=100000, allowed=True)
        for r, price in zip(rows, (11, 10.5, 10.1))
    }
    for q in points.values():
        q.update(
            buyPrice1=q["trade"],
            buyVol1=10000,
            sellPrice1=0 if q["trade"] == 11 else q["trade"],
            sellVol1=0 if q["trade"] == 11 else 10000,
        )
    status, pick, trace = choose(rows, points.__getitem__)
    assert status == "selected" and pick["code"] == rows[2]["code"] and len(trace) == 3
    points[rows[0]["code"]]["trade"] = 10.9
    assert choose(rows, points.__getitem__)[:2] == ("first_not_sealed", None)


def test_live_fee_and_missing_exposure_stop_risk():
    actual = dict(
        status="closed",
        bought=100,
        sold=100,
        code=CODE,
        actual_realized_net=None,
        buy_gross=2000,
        sell_gross=1720,
        buy_cost_to_date=8,
        sell_cost_to_date=0.172,
    )
    assert pair.split_risk({"a": {"actual": actual}}, {}, None)["paused"]
    previous = {
        "split_trials": {
            "a": {"actual": dict(status="open_or_reconciling", bought=100, sold=0)}
        }
    }
    actual.update(sell_gross=2000)
    risk = pair.split_risk(
        {"a": {"actual": actual}}, {}, previous, ["2026-12-01"], "2026-12-02"
    )
    assert risk["paused"] and risk["missing_exposed_dates"] == ["2026-12-01"]


def test_limit_trade_with_an_offer_keeps_cash():
    from research_relay_walkdown import choose

    row = dict(code=CODE, codeName="股票", isPreSt=0, jsjl=8, xcjw=350)
    quote = dict(
        open=10,
        trade=11,
        up=11,
        down=9,
        allowed=True,
        vol=40000,
        buyPrice1=11,
        buyVol1=3000,
        sellPrice1=11,
        sellVol1=200,
    )
    assert choose([row], lambda _: quote)[0] == "first_not_sealed"


def test_observed_relay_cash_matches_executable_ask_and_one_visible_lot(
    tmp_path, monkeypatch
):
    from research_relay_walkdown import close
    import research_relay_walkdown as walk

    folder = tmp_path / "day_limit_pair"
    folder.mkdir()
    decision = dict(
        day=DAY,
        protocol=walk.PROTOCOL["id"],
        status="selected",
        observed_at=pair.at(DAY, "0945").isoformat(),
        rank_sha256="a" * 64,
        candidate=dict(code=CODE, cap=10.5, up=12, down=8),
    )
    decision["sha256"] = pair.sha(pair.encode(decision))
    (folder / (DAY + ".relay-decision.json")).write_bytes(pair.encode(decision))
    rec = dict(
        day=DAY,
        protocol=walk.PROTOCOL["id"],
        status="selected",
        decision=decision,
        observed_at=pair.at(DAY, "0946").isoformat(),
        point=dict(trade=9.8, vol=1e7, ask_price=10, ask_shares=100),
    )
    rec["sha256"] = pair.sha(pair.encode(rec))
    (folder / (DAY + ".relay-entry.json")).write_bytes(pair.encode(rec))
    monkeypatch.setattr(walk, "ranked", lambda *a: ([], "a" * 64))
    b = close(folder, DAY, None, {CODE: {"trade": 10, "vol": 10000}}, {})
    event = b["effects"]["normal"]["entry"]
    assert event["shares"] == 100 and event["price"] == 10.01


@pytest.mark.app_simulation
def test_separate_actual_child_savings_and_late_fee_proof(tmp_path, monkeypatch):
    from tests.test_entry_clock_app_pilot import ordinary, split, T

    p = ordinary()
    state = tmp_path / "book_b_live_execution"
    pair.pilot.enable(state, T)
    early = split(state, [p])[0]
    doc, _, _ = pair.pilot.load_assignment(state, DAY)
    candidate = dict(
        CAND, code=early.code, plan_hash=early.plan_hash, assignment=doc["sha256"]
    )
    actual = dict(
        status="closed",
        bought=100,
        sold=100,
        buy_gross=960,
        buy_actual_fee=None,
        actual_realized_net=None,
    )
    from xiaocao.research import split_evidence

    monkeypatch.setattr(split_evidence, "collect", lambda *a: {"sample": "test"})
    monkeypatch.setattr(split_evidence, "verify", lambda *a: None)
    monkeypatch.setattr(pair, "actual_child", lambda *a: dict(actual))
    trials = pair.observe_splits(
        tmp_path,
        tmp_path,
        DAY,
        None,
        candidate,
        {early.code: prices("0935")},
        {early.code: {"trade": 10, "vol": 10000}},
        {},
    )
    item = trials[DAY]
    assert (
        item["estimated_entry_saving_yuan"]["normal"] > 0
        and item["entry_saving_yuan"]["normal"] is None
    )
    assert item["net_difference_yuan"]["normal"] is None
    actual.update(buy_actual_fee=1.5, actual_realized_net=120)
    later = pair.observe_splits(
        tmp_path,
        tmp_path,
        NEXT,
        {"split_trials": trials},
        None,
        {},
        {early.code: {"trade": 10, "vol": 100000}},
        {early.code: {"down": 8, "bid_shares": 1000}},
    )
    assert later[DAY]["entry_saving_yuan"]["normal"] == round(
        item["entries"]["normal"]["basis"] / 100 - 961.5, 2
    )
    assert later[DAY]["net_difference_yuan"]["normal"] == round(
        120 - later[DAY]["arms"]["normal"]["realized"] / 100, 2
    )
