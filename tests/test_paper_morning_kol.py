"""Paper support owns no trading writer and never waits with a ledger lease."""

import pytest

from tests.test_kol_opening_preparation import case, NOW, save, accept
from xiaocao.kol import opening_preparation as prep
from xiaocao.runner_recovery import _hash
from xiaocao.live import paper_morning_kol as paper


@pytest.fixture
def owner(case, monkeypatch):
    binding = {"trade_date": "2026-10-23", "owner_thread_id": "owner", "run_id": "original-run",
               "automation_id": "xiaocao-daily-morning-execution"}
    case["inputs"]["binding"] = binding
    save(case["path"], case["inputs"])
    case["draft"]["input_sha256"] = _hash(case["inputs"])
    case["review"]["draft_sha256"] = prep.canonical_sha256(case["draft"])
    case["dispatch"].update(binding=binding, input_sha256=_hash(case["inputs"]))
    case["review"]["dispatch_sha256"] = prep.canonical_sha256(case["dispatch"])
    run = case["root"] / "output/live/auto/runs/original-run"
    save(run / "manifest.json", {"market_date": binding["trade_date"], "thread_id": "owner",
         "automation_id": binding["automation_id"], "run_id": "original-run"})
    monkeypatch.setenv("CODEX_THREAD_ID", "owner")
    monkeypatch.setenv("CODEX_AUTOMATION_ID", binding["automation_id"])
    prepared = accept(case)
    path = save(case["root"] / "prepared.json", prepared)
    paper.register_preparation(case["root"], path, prepared)
    monkeypatch.setattr(paper, "build_trading_context", lambda **kw: {})
    monkeypatch.setattr(paper, "write_trading_projection", lambda *a, **kw: case["inputs"]["projection"])
    monkeypatch.setattr(paper, "read_consumed_rows", lambda *a, **kw: [{"code":"002172", "mode":"N字低吸"}])
    clock = [NOW.replace(minute=25, second=30)]
    freeze = {"snapshot_sha256": "b"*64, "checkpoint_sha256": "c"*64, "strategy_sha": "d"*40}
    events = []
    return case, run, freeze, clock, events


def start(owner, factor=1):
    case, run, freeze, clock, events = owner
    return paper.PaperKolReview(case["root"], run, "2026-10-23", freeze,
        now=lambda:clock[0], preview=lambda root, **kw: ({"authority":"preview_only"}, {"deploy_factor":factor}), emit=events.append)


def test_current_request_waits_for_bound_policy_and_records_adoption_evidence(owner, monkeypatch):
    review = start(owner)
    assert owner[4][0]["event"] == "paper_kol_review_requested"
    monkeypatch.setattr(paper.kol_policy, "load_decision", lambda *a: {"status":"no_decision"})
    assert not review.tick()
    record = {"decision":{"as_of":owner[3][0].isoformat(),"morning_request_sha256":"wrong"},
              "review":{"morning_request_sha256":"wrong"}}
    policy = {"status":"validated","decision_sha256":"e"*64,"record":record}
    monkeypatch.setattr(paper.kol_policy, "load_decision", lambda *a: policy)
    assert not review.tick()
    for row in record.values(): row["morning_request_sha256"] = review.request["request_sha256"]
    assert review.tick()
    observed = paper.read_support(review.path, "2026-10-23", owner[2], owner[1])
    assert observed["status"] == "validated"
    assert observed["request_sha256"] == owner[4][0]["request_sha256"]
    assert start(owner).tick()  # same original receipt, no second request
    assert len(owner[4]) == 1


def test_paper_support_keeps_original_0927_cutoff(owner, monkeypatch):
    review = start(owner)
    monkeypatch.setattr(paper.kol_policy, "load_decision", lambda *a: {"status":"no_decision"})
    owner[3][0] = NOW.replace(minute=27)
    assert review.tick()
    assert review.receipt["status"] == "timed_out"
    assert review.receipt["max_wait_seconds"] == 90


@pytest.mark.parametrize("cause", ["risk", "missing", "late"])
def test_support_degrades_before_model_wait(owner, cause):
    if cause == "missing": (owner[1]/"kol-preparation.json").unlink()
    if cause == "late": owner[3][0] = NOW.replace(minute=28)
    review = start(owner, factor=0 if cause == "risk" else 1)
    assert review.tick() and not owner[4]
    assert review.receipt["status"] == ("not_required" if cause == "risk" else "deferred")


def test_registration_and_receipt_cannot_cross_owners_or_freezes(owner, monkeypatch):
    review = start(owner, factor=0)
    changed = {**owner[2], "snapshot_sha256":"f"*64}
    with pytest.raises(ValueError): paper.read_support(review.path, "2026-10-23", changed, owner[1])
    monkeypatch.setenv("CODEX_THREAD_ID", "other")
    with pytest.raises(ValueError): paper.read_support(review.path, "2026-10-23", owner[2], owner[1])


def test_shorter_original_wait_budget_is_not_refunded(owner, monkeypatch):
    case, run, freeze, clock, events = owner
    review = paper.PaperKolReview(case["root"], run, "2026-10-23", freeze,
        now=lambda:clock[0], preview=lambda root, **kw: ({}, {"deploy_factor":1}), emit=events.append, budget_seconds=5)
    assert review.receipt is None
    assert review.request["max_wait_seconds"] == 5
    clock[0] = clock[0].replace(second=35)
    assert review.tick() and review.receipt["status"] == "timed_out"


def test_preview_finishing_after_cutoff_never_dispatches(owner):
    case, run, freeze, clock, events = owner
    def slow(root, *, deadline):
        clock[0] = deadline
        return {}, {"deploy_factor":1}
    review = paper.PaperKolReview(case["root"], run, "2026-10-23", freeze,
        now=lambda:clock[0], preview=slow, emit=events.append)
    assert review.receipt["status"] == "deferred"
    assert not events


def test_preview_read_only_child_and_blocked_lock_are_bounded(tmp_path):
    from datetime import datetime, timedelta
    import time
    from tests.test_paper_decision_support import account
    live = tmp_path / "output/live"
    path = save(live / "paper_account.json", account())
    before = path.read_bytes()
    facts, risk = paper.account_preview(tmp_path, deadline=datetime.now(paper.A_SHARE_TZ)+timedelta(seconds=5))
    assert facts["authority"] == risk["authority"] == "preview_only"
    assert path.read_bytes() == before
    assert not (paper.paper.risk_directory(tmp_path) / "risk_latest.json").exists()
    with paper.paper.paper_ledger_lock(tmp_path):
        started = time.monotonic()
        with pytest.raises(ValueError, match="PAPER_KOL_PREVIEW_DEADLINE"):
            paper.account_preview(tmp_path, deadline=datetime.now(paper.A_SHARE_TZ)+timedelta(seconds=0.5))
        assert time.monotonic()-started < 2


def test_owner_sigterm_reaps_isolated_preview_before_terminating(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time
    code = '''
import sys
from pathlib import Path
from datetime import datetime, timedelta
from xiaocao.live import paper_morning_kol as p
original = p.subprocess.Popen
def observed(*args, **kwargs):
    child = original(*args, **kwargs)
    Path(sys.argv[2]).write_text(str(child.pid))
    return child
p.subprocess.Popen = observed
p.account_preview(Path(sys.argv[1]), deadline=datetime.now(p.A_SHARE_TZ)+timedelta(seconds=10))
'''
    pidfile = tmp_path / "preview.pid"
    with paper.paper.paper_ledger_lock(tmp_path):
        with subprocess.Popen([sys.executable, "-c", code, str(tmp_path), str(pidfile)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as owner_process:
            try:
                until = time.monotonic()+3
                while not pidfile.exists() and time.monotonic() < until:
                    time.sleep(0.01)
                assert pidfile.exists()
                preview_pid = int(pidfile.read_text())
                owner_process.terminate()
                owner_process.communicate(timeout=2)
                assert owner_process.returncode == -signal.SIGTERM
                with pytest.raises(ProcessLookupError): os.kill(preview_pid, 0)
            finally:
                if owner_process.poll() is None:
                    owner_process.kill()
                    owner_process.communicate()


def test_original_request_assembles_exact_ready_to_send_warm_handoff(owner):
    review = start(owner)
    event = owner[4][0]
    from pathlib import Path
    import json
    handoff = json.loads(Path(event['dispatch_path']).read_bytes())
    assert handoff['authority'] == 0 and handoff['actual_dispatch'] == 'not_observed'
    assert handoff['request_sha256'] == review.request['request_sha256']
    assert handoff['packet']['packet_sha256'] == review.request['kol_inputs']['packet_sha256']
    assert handoff['tool_arguments']['target'] == handoff['packet']['worker_id']
    assert handoff['brief']['account_risk'] == review.request['account_risk']
    assert handoff['cutoff'] == review.cutoff.isoformat()
    assert not (owner[0]['root']/'output/live/kol_policy/decisions').exists()


def test_warm_handoff_rejects_stale_account_facts_and_late_dispatch(owner,monkeypatch):
    from copy import deepcopy
    from xiaocao.live.morning_dispatch import write_warm_dispatch
    review=start(owner)
    request=deepcopy(review.request)
    request['account_facts']['changed_after_packet']=True
    with pytest.raises(ValueError,match='PACKET_BINDING_MISMATCH'):
        write_warm_dispatch(request,owner[1]/'changed.request.json',now=owner[3][0])
    with pytest.raises(ValueError,match='ORIGINAL_CUTOFF'):
        write_warm_dispatch(review.request,owner[1]/'late.request.json',now=review.cutoff)


@pytest.mark.app_simulation
def test_app_relative_default_paths_use_same_real_packet_facts(owner,monkeypatch):
    from datetime import timedelta
    from pathlib import Path
    import importlib,json
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    cli=importlib.import_module('scripts.book_b_live_morning')
    case,run,freeze,clock,events=owner
    monkeypatch.chdir(case['root'])
    original={'trade_date':'2026-10-23','runtime':'live','book':'B',
        'requested_at':clock[0].isoformat(),'review_wait_until':(clock[0]+timedelta(seconds=10)).isoformat(),
        'entry_deadline':(clock[0]+timedelta(minutes=5)).isoformat(),'max_wait_seconds':10,
        'freeze_path':'output/live/freeze.jsonl','policy_root':'output/live/kol_policy/decisions',
        'freeze_sha256':freeze['snapshot_sha256'],'strategy_sha':freeze['strategy_sha'],
        'candidates':[{'code':'002172','mode':'N字低吸'}],'account_facts':{'cash':1000},'account_risk':{'deploy_factor':1}}
    normalized=cli._normalized_review_request(original)
    ready=json.loads((run/'kol-preparation.json').read_text())
    packet=prep.opening_packet(Path(ready['preparation_path']),case['path'],normalized,now=clock[0])
    packet_path=save(run/'app-packet.json',packet)
    normalized['kol_inputs']={'packet_path':str(packet_path),'packet_sha256':packet['packet_sha256'],
                              'warm_worker':packet['worker_id']}
    elapsed=[0.]
    result=cli._review_rendezvous(normalized,now=lambda:clock[0]+timedelta(seconds=elapsed[0]),
        monotonic=lambda:elapsed[0],sleep=lambda seconds:elapsed.__setitem__(0,elapsed[0]+seconds))
    assert result['dispatch']['status']=='assembled_not_dispatched' and result['dispatch']['error'] is None
    handoff=json.loads(Path(result['dispatch']['path']).read_bytes())
    assert handoff['packet']['request_facts_sha256']==prep.canonical_sha256(cli._normalized_review_request(original))
