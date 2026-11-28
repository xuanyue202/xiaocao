import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
