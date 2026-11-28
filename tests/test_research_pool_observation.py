import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from xiaocao.research import pool_observation as obs

DAY = "2026-12-01"
PREV = "2026-11-30"
OLD = ["000001.XSHE"]
NEW = ["000002.XSHE"]


class Clock:
    def __init__(self, t):
        self.value = datetime.fromisoformat(DAY + "T" + t).replace(
            tzinfo=ZoneInfo("Asia/Shanghai")
        )

    def now(self):
        return self.value

    def sleep(self, n):
        self.value += timedelta(seconds=n)


class Quotes:
    def __init__(self, clock):
        self.clock = clock
        self.reads = []

    def get_code_list_v2(self, day, group, hpqb, lpdx):
        self.reads.append((day, group))
        return list(
            OLD if (day == PREV or self.clock.now().strftime("%H%M") == "0927") else NEW
        )

    def sort_v2(self, codes, sort_id, date):
        assert sort_id == 37 and date == DAY
        return ["600519.XSHG", *reversed(codes)]

    def get_xiao_cao_index_v2(self, day, codes):
        assert day == DAY and len(codes) <= 80
        return [
            {"code": c, "jsjl": -12.5, "xcjw": int(c[:6]), "tradeDate": int(day.replace("-", ""))}
            for c in reversed(codes)
        ]


def test_natural_memberships_and_exact_comparisons(tmp_path, monkeypatch):
    clock = Clock("09:26:00")
    q = Quotes(clock)
    monkeypatch.setattr(
        obs,
        "opening_members",
        lambda *_: {"pools": {g: {"codes": OLD} for g in obs.GROUPS}},
    )

    def observe(early):
        return obs.observe_session(
            tmp_path,
            tmp_path,
            DAY,
            PREV,
            early,
            "unused",
            clock=clock.now,
            sleep=clock.sleep,
            client=q,
        )

    assert all(v["complete"] for v in observe(True).values())
    assert len(q.reads) == 9
    observe(True)
    clock.value = clock.value.replace(hour=15, minute=22)
    assert observe(False)["1517"]["complete"]
    assert len(q.reads) == 15
    r = json.loads((tmp_path / DAY / "1517.json").read_text())
    assert r["relay_ranking"]["ordered_codes"] == NEW
    assert r["relay_ranking"]["status"] == "observed"
    by = r["comparisons"]["jieli"]
    assert (
        by["opening"]["prior_date"]["equal"]
        and not by["opening"]["same_date_afternoon"]["equal"]
    )
    assert (
        by["0927"]["prior_date"]["equal"] and by["0932"]["same_date_afternoon"]["equal"]
    )
    observe(False)
    assert len(q.reads) == 15

    # Original membership-only receipts keep their evidence and never trigger late reads.
    path = tmp_path / DAY / "1517.json"
    r.pop("relay_ranking")
    r.pop("receipt_sha256")
    r["receipt_sha256"] = hashlib.sha256(obs.encoded(r)).hexdigest()
    legacy = obs.encoded(r)
    path.write_bytes(legacy)
    summary = observe(False)["1517"]
    assert summary["complete"] and summary["relay_rank_status"] == "legacy_unobserved"
    assert path.read_bytes() == legacy and len(q.reads) == 15


def test_missed_windows_and_empty_never_match(tmp_path, monkeypatch):
    clock = Clock("15:32:03")
    q = Quotes(clock)
    monkeypatch.setattr(
        obs,
        "opening_members",
        lambda *_: {"pools": {g: {"codes": OLD} for g in obs.GROUPS}},
    )
    result = obs.observe_session(
        tmp_path,
        tmp_path,
        DAY,
        PREV,
        False,
        "unused",
        clock=clock.now,
        sleep=clock.sleep,
        client=q,
    )
    assert not q.reads and not result["1517"]["complete"]
    r = json.loads((tmp_path / DAY / "1517.json").read_text())
    assert r["comparisons"]["dixi"]["0932"]["same_date_afternoon"] is None
    assert obs.membership_match([], []) is None


def test_late_and_failed_provider_reads_remain_gaps():
    clock = Clock("09:27:00")

    class Mixed:
        def get_code_list_v2(self, day, group, *args):
            if group == "jieli":
                raise OSError("unavailable")
            if group == "dixi":
                return []
            clock.sleep(61)
            return NEW

    items = obs.fetch_pools(
        Mixed(), DAY, clock.now() + timedelta(seconds=60), clock.now
    )
    assert [r["status"] for r in items.values()] == [
        "read_error",
        "empty_unconfirmed",
        "late_response",
    ]


def test_misplaced_intact_receipt_cannot_supply_a_different_slot(tmp_path, monkeypatch):
    clock = Clock("09:26:00")
    q = Quotes(clock)
    monkeypatch.setattr(
        obs,
        "opening_members",
        lambda *_: {"pools": {g: {"codes": OLD} for g in obs.GROUPS}},
    )

    def run(early):
        return obs.observe_session(
            tmp_path,
            tmp_path,
            DAY,
            PREV,
            early,
            "unused",
            clock=clock.now,
            sleep=clock.sleep,
            client=q,
        )

    run(True)
    d = tmp_path / DAY
    (d / "0932.json").write_bytes((d / "0927.json").read_bytes())
    assert run(True)["0932"]["error"] == "receipt_identity_mismatch"
    assert not run(False)["1517"]["complete"]
    close = json.loads((d / "1517.json").read_bytes())
    assert close["morning_receipt_errors"]["0932"] == "receipt_identity_mismatch"
    assert close["comparisons"]["jieli"]["0932"]["prior_date"] is None


def test_large_relay_pool_uses_supplier_order_and_links_each_score_to_its_code():
    clock = Clock("09:32:01")
    codes = [f"{i:06}.XSHE" for i in range(1, 90)]
    pool = {"status": "observed", "codes": codes}
    rank = obs.observe_relay_ranking(
        Quotes(clock), DAY, pool, clock.now() + timedelta(seconds=59), clock.now
    )
    assert rank["status"] == "observed" and rank["ordered_codes"] == codes[::-1]
    assert rank["stocks"] == [
        {"code": c, "jsjl": -12.5, "xcjw": int(c[:6]), "provider_trade_day": DAY}
        for c in codes[::-1]
    ]
    assert [s["kind"] for s in rank["reads"]] == ["sort:37", "stock_index", "stock_index"]


@pytest.mark.parametrize(
    "issue,expected",
    [
        ("duplicate", "incomplete_ranking"),
        ("wrong_stock", "score_identity_mismatch"),
        ("missing", "missing_scores"),
        ("stale", "score_date_mismatch"),
        ("conflict", "score_date_mismatch"),
        ("invalid_date", "invalid_score_date"),
        ("late", "late_response"),
        ("unavailable", "pool_unavailable"),
    ],
)
def test_incomplete_relay_observations_remain_gaps(issue, expected):
    clock = Clock("09:32:01")

    class Incomplete(Quotes):
        def sort_v2(self, codes, sort_id, date):
            if issue == "duplicate":
                return codes * 2
            return super().sort_v2(codes, sort_id, date)

        def get_xiao_cao_index_v2(self, day, codes):
            if issue == "late":
                clock.sleep(60)
            code = OLD[0] if issue == "wrong_stock" else codes[0]
            row = {"code": code, "jsjl": 0, "xcjw": None}
            if issue in ("stale", "conflict"):
                row["trade_date"] = PREV
            if issue == "conflict":
                row["tradeDate"] = DAY
            if issue == "invalid_date":
                row["tradeDate"] = "2026-14-31"
            return [row]

    pool = {"status": "read_error" if issue == "unavailable" else "observed", "codes": NEW}
    rank = obs.observe_relay_ranking(
        Incomplete(clock), DAY, pool, clock.now() + timedelta(seconds=59), clock.now
    )
    assert rank["status"] == expected
    if issue == "missing":
        assert rank["stocks"][0] == {
            "code": NEW[0], "jsjl": 0, "xcjw": None, "provider_trade_day": None,
        }
    else:
        assert rank["stocks"] == []
