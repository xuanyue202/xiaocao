from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from xiaocao.kol import human_playback as human
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.xiaocao_wechat import XiaocaoLiveCaptureDriver

NOW = datetime(2026, 10, 26, 14, tzinfo=timezone.utc)


def test_human_backoff_caps_at_five_minutes_and_rejects_naive_state():
    assert [(human.next_human_poll(NOW, i) - NOW).total_seconds() for i in range(9)] == [10,20,40,80,160,300,300,300,300]
    with pytest.raises(EnrichmentError):
        human.next_human_poll(NOW.replace(tzinfo=None), 0)
    with pytest.raises(EnrichmentError):
        human.next_human_poll(NOW, -1)


def test_native_action_question_is_exact_once_and_never_launches_local_popup(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(human.subprocess, 'run', lambda *a, **kw: pytest.fail('no custom notifier'))
    monkeypatch.setattr(human.subprocess, 'Popen', lambda *a, **kw: pytest.fail('no custom popup'))
    receipt = tmp_path / 'notification.json'
    for _ in range(2):
        human.request_human_action_once(receipt, published_at='今天早场',
                                        identity='original', capture_job_id='capture-original')
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(events) == 1
    assert events[0]['event'] == 'daily_human_action_required'
    assert events[0]['identity'] == 'original' and events[0]['capture_job_id'] == 'capture-original'
    assert json.loads(receipt.read_text()) == {'state':'codex_question_requested','display_verified':False}
    assert receipt.stat().st_mode & 0o777 == 0o600


def entry_files(tmp_path):
    item = dict(identity='original', capture_job_id='capture-original', mini_program_name='见势擒龙团', mini_program_token='token', message_sha256='abc')
    config = dict(playback_operator='human', editor_url='https://console.cli.im/editor', last_configured_subscription_id='original', last_configured_message_sha256='abc', public_url='https://qr61.cn/original', provider_path='/pages/code/code', provider_app_id='wxoriginal', provider_org_coding='org')
    proof = dict(identity='original', capture_job_id='capture-original', saved_target='#小程序://见势擒龙团/token', component_reopened=True, editor_url=config['editor_url'], observed_at=NOW.isoformat())
    config_path, proof_path = tmp_path / 'bridge.json', tmp_path / 'proof.json'
    config_path.write_text(json.dumps(config)); proof_path.write_text(json.dumps(proof))
    return item, config, config_path, proof_path


def test_entry_launch_is_claimed_once_and_does_not_persist_ticket(tmp_path, monkeypatch):
    import requests
    item, config, path, proof = entry_files(tmp_path)
    calls = []
    class Response:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data
    page = config['provider_path'] + '?' + urlencode(dict(q=config['public_url'], trigger='h5_wx_block', f='schema'))
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: Response({'data': {'wx_url_scheme': dict(appId='wxoriginal', appPath=page, fetchUrl='https://wxurlgenerator.cli.im/original')}}))
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: Response({'data': {'urlScheme': 'weixin://dl/business/?t=private-ticket'}}))
    monkeypatch.setattr(human.subprocess, 'run', lambda args, **kw: calls.append(args))
    receipt = tmp_path / 'entry.json'
    result = human.launch_verified_caoliao(config_path=path, item=item, proof_path=proof, receipt_path=receipt, now=NOW)
    assert result['entry_launched'] is True
    assert calls == [['/usr/bin/open', 'weixin://dl/business/?t=private-ticket']]
    assert 'private-ticket' not in receipt.read_text()
    with pytest.raises(EnrichmentError, match='already claimed'):
        human.launch_verified_caoliao(config_path=path, item=item, proof_path=proof, receipt_path=receipt, now=NOW)
    assert len(calls) == 1


@pytest.mark.parametrize('bad', ['stale', 'other_capture', 'other_target'])
def test_entry_rejects_unverified_saved_target_before_any_effect(tmp_path, monkeypatch, bad):
    item, config, path, proof = entry_files(tmp_path)
    value = json.loads(proof.read_text())
    if bad == 'stale': value['observed_at'] = (NOW - timedelta(minutes=4)).isoformat()
    if bad == 'other_capture': value['capture_job_id'] = 'different'
    if bad == 'other_target': value['saved_target'] += 'other'
    proof.write_text(json.dumps(value))
    monkeypatch.setattr(human.subprocess, 'run', lambda *a, **kw: pytest.fail('no launch'))
    receipt = tmp_path / 'entry.json'
    with pytest.raises(EnrichmentError, match='unverified'):
        human.launch_verified_caoliao(config_path=path, item=item, proof_path=proof, receipt_path=receipt, now=NOW)
    assert not receipt.exists()


def candidate(live='l_original', **kwargs):
    return dict(id='fresh', live_id=live, captured=(NOW+timedelta(seconds=1)).isoformat(), media_type='m3u8', url='https://vod.xet.tech/replay/playlist_eof.m3u8', source_url='https://apporiginal.h5.xiaoeknow.com/_alive/v3/get_lookback_list', **kwargs)


@pytest.mark.parametrize('case', ['stale', 'live', 'ambiguous', 'expected_other', 'fresh'])
def test_human_observation_filters_before_exact_source_binding(monkeypatch, case):
    rows = [candidate()]
    if case == 'stale': rows[0]['captured'] = (NOW-timedelta(seconds=1)).isoformat()
    if case == 'live': rows[0]['url'] = 'https://liveplay-mp.xiaoeknow.com/live/stream.m3u8'
    if case == 'ambiguous':
        rows.append(candidate('l_other'))
        for row in rows: row['source_url'] = row['source_url'].replace('apporiginal', 'appsnm3rlcp3566')
    driver = object.__new__(XiaocaoLiveCaptureDriver)
    monkeypatch.setattr(driver, '_service', lambda identity: SimpleNamespace(sniffer=SimpleNamespace(candidates=lambda: rows)))
    binds = []
    monkeypatch.setattr(driver, 'bind_mini_program_capture', lambda *a, **kw: binds.append((a,kw)))
    result = driver.observe_human_playback('original', 'capture-original', observed_after=NOW, expected_source='xiaoetong:appother:l_original' if case=='expected_other' else ('xiaoetong:apporiginal:l_original' if case!='ambiguous' else ''))
    assert result['observed'] is (case == 'fresh')
    if case == 'fresh':
        assert binds[0][0] == ('original', 'capture-original')
        assert binds[0][1]['observed_after'] == NOW
    else: assert binds == []


def test_unbound_human_media_never_binds_an_unrelated_or_unconfirmed_course(monkeypatch):
    rows = [candidate()]
    driver = object.__new__(XiaocaoLiveCaptureDriver)
    monkeypatch.setattr(driver, '_service', lambda _: SimpleNamespace(sniffer=SimpleNamespace(candidates=lambda: rows)))
    monkeypatch.setattr(driver, 'bind_mini_program_capture', lambda *a, **kw: pytest.fail('unconfirmed media must not bind'))
    assert driver.observe_human_playback('original','capture-original',observed_after=NOW)['reason'] == 'media_pending'
    rows[0]['source_url'] = rows[0]['source_url'].replace('apporiginal','appsnm3rlcp3566')
    result = driver.observe_human_playback('original','capture-original',observed_after=NOW)
    assert result['reason'] == 'source_confirmation_required' and result['observed'] is False


def test_network_owner_is_exclusive_before_snapshot_and_preserves_unchanged_proxy(tmp_path, monkeypatch):
    import io
    from xiaocao.yangsheng import network
    config = tmp_path/'bridge.json'; config.write_text('{"playback_operator":"human"}')
    snapshots, restores = [], []
    class Guard:
        stdin = io.StringIO()
        stdout = io.StringIO('armed\n')
        def wait(self, **kwargs): return 0
    monkeypatch.setattr(human.subprocess, 'Popen', lambda *a, **kw: Guard())
    monkeypatch.setattr(human.select, 'select', lambda *args: ([Guard.stdout],[],[]))
    monkeypatch.setattr(network, 'snapshot', lambda: snapshots.append(True) or {'pac':'Enabled: No\nURL: original'})
    monkeypatch.setattr(network, 'restore', lambda *args: restores.append(args) or {'restored':True})
    with human.human_capture_network_owner(config):
        with pytest.raises(EnrichmentError, match='owner busy'):
            with human.human_capture_network_owner(config): pytest.fail('must not enter')
        assert len(snapshots)==1 and restores==[]
    assert len(restores)==1


def test_proxy_restore_without_change_issues_no_network_mutation(monkeypatch):
    from xiaocao.yangsheng import network
    before = {'pac':'Enabled: Yes\nURL: http://127.0.0.1:2023/proxy.pac'}
    monkeypatch.setattr(network, 'snapshot', lambda: before.copy())
    monkeypatch.setattr(network, 'command', lambda *a: pytest.fail('unchanged proxy must not be toggled'))
    assert network.restore(before,'http://127.0.0.1:2023/proxy.pac')['restored']


def test_real_binder_rejects_candidate_before_human_entry_despite_old_capture(monkeypatch, tmp_path):
    from xiaocao.kol.capture import CaptureJobStore
    store = CaptureJobStore(tmp_path/'capture.jsonl')
    job = store.arm([])
    job = store.transition(job, 'test_clock', created_at=(NOW-timedelta(hours=1)).isoformat())
    row = candidate(); row['captured'] = (NOW-timedelta(seconds=1)).isoformat()
    driver = object.__new__(XiaocaoLiveCaptureDriver)
    monkeypatch.setattr(driver, '_service', lambda _: SimpleNamespace(capture_store=store, sniffer=SimpleNamespace(candidates=lambda: [row])))
    with pytest.raises(EnrichmentError, match='predates its arm'):
        driver.bind_mini_program_capture('original',job['job_id'],source_identity='xiaoetong:apporiginal:l_original',candidate_id='fresh',observed_after=NOW)
    assert not store.latest(job['job_id']).get('expected_source')
