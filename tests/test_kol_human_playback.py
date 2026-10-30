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


def test_native_action_notice_is_exact_once_without_required_reply_or_local_popup(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(human.subprocess, 'run', lambda *a, **kw: pytest.fail('no custom notifier'))
    monkeypatch.setattr(human.subprocess, 'Popen', lambda *a, **kw: pytest.fail('no custom popup'))
    receipt = tmp_path / 'notification.json'
    entry = tmp_path / 'entry.json'
    entry.write_text(json.dumps(dict(identity='original',capture_job_id='capture-original',entry_launched=True,armed_at=NOW.isoformat())))
    for _ in range(2):
        human.request_human_action_once(receipt, published_at='今天早场',
                                        identity='original', capture_job_id='capture-original',entry_receipt=entry)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(events) == 1
    assert events[0]['event'] == 'daily_human_action_required'
    assert events[0]['identity'] == 'original' and events[0]['capture_job_id'] == 'capture-original'
    assert events[0]['response_required'] is False
    assert json.loads(receipt.read_text()) == {'state':'codex_action_notice_requested','display_verified':False}
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
    assert result['reason'] == 'course_metadata_unverified' and result['observed'] is False


@pytest.mark.parametrize('bad', ['', 'title', 'date', 'session', 'missing_time', 'title_date',
                                  'unrelated', 'compact_date', 'iso_date'])
def test_course_metadata_uses_merchant_title_and_original_session(bad):
    candidate = {'title':'盘前大师班直播10月27日'}
    lineage = {'course_title':candidate['title'], 'course_start_at':1793064000,
               'metadata_anchors':[{'base_info_sha256':'a'*64}]}
    if bad == 'title': candidate['title'] = '另一门课'
    if bad == 'date': lineage['course_start_at'] -= 86400
    if bad == 'session': lineage['course_start_at'] += 9*3600
    if bad == 'missing_time': lineage.pop('course_start_at')
    if bad == 'title_date':
        candidate['title'] = lineage['course_title'] = '盘前大师班直播10月26日'
    if bad == 'unrelated': candidate['title'] = lineage['course_title'] = '无关课程'
    if bad == 'compact_date': candidate['title'] = lineage['course_title'] = '20261026 盘前大师班'
    if bad == 'iso_date': candidate['title'] = lineage['course_title'] = '2026-10-26 盘前大师班'
    if bad:
        with pytest.raises(EnrichmentError):
            human.verify_course_metadata(candidate,lineage,'2026-10-27T08:33:00+08:00')
    else:
        proof = human.verify_course_metadata(candidate,lineage,'2026-10-27T08:33:00+08:00')
        assert proof['method'] == 'merchant_title_and_session'
        assert proof['title'] == candidate['title']


@pytest.mark.parametrize('title,accepted', [
    ('大师班专场(18：00开播)', True),
    ('大师班专场（ 🔔️18:00 开播 ）', True),
    ('大师班专场(19：00开播)', False),
    ('另一大师班专场(18：00开播)', False),
    ('大师班专场(18：00开播)10月26日', False),
    ('🔔️', False),
])
def test_course_metadata_accepts_only_observed_display_formatting(title, accepted):
    lineage = {'course_title': '大师班专场（🔔18:00开播）',
               'course_start_at': 1793095200, 'metadata_anchors': []}
    if not accepted:
        with pytest.raises(EnrichmentError):
            human.verify_course_metadata({'title': title}, lineage, '2026-10-27T16:37:00+08:00')
        return
    proof = human.verify_course_metadata({'title': title}, lineage, '2026-10-27T16:37:00+08:00')
    assert proof['title'] == title
    assert proof['merchant_title'] == lineage['course_title']
    with pytest.raises(EnrichmentError):
        human.verify_course_metadata({'title': title}, lineage, '2026-10-26T16:37:00+08:00')


@pytest.mark.parametrize('title,merchant_title', [
    ('大师班专场10 月26日(18：00开播)', '大师班专场10月26日（🔔18:00开播）'),
    ('大师班专场(18:00开播)2026－10－26', '大师班专场（🔔18:00开播）2026-10-26'),
    ('大师班专场①(18：00开播)', '大师班专场1（🔔18:00开播）'),
])
def test_course_title_formatting_preserves_conflicting_dates_and_number_labels(title, merchant_title):
    lineage = {'course_title': merchant_title, 'course_start_at': 1793095200,
               'metadata_anchors': []}
    with pytest.raises(EnrichmentError):
        human.verify_course_metadata({'title': title}, lineage, '2026-10-27T16:37:00+08:00')


def test_unbound_exact_title_verifies_before_binding_without_human(monkeypatch, tmp_path):
    import xiaocao.kol.xiaocao_wechat as wechat
    row = candidate(title='盘前大师班直播10月27日')
    row['source_url'] = 'https://xet.kj1team.cn/_alive/v2/get_lookback_url'
    driver = object.__new__(XiaocaoLiveCaptureDriver)
    monkeypatch.setattr(driver,'_service',lambda _:SimpleNamespace(
        sniffer=SimpleNamespace(candidates=lambda:[row]),sniffer_binary=tmp_path/'sniffer'))
    monkeypatch.setattr(wechat,'_native_v2_merchant_lineage',lambda *a,**kw:{
        'course_title':row['title'],'course_start_at':1793064000,'metadata_anchors':[{'base_info_sha256':'a'*64}]})
    binds=[]
    monkeypatch.setattr(driver,'bind_mini_program_capture',lambda *a,**kw:binds.append((a,kw)))
    result=driver.observe_human_playback('original','capture-original',observed_after=NOW,
        published_at='2026-10-27T08:33:00+08:00')
    assert result['observed'] is True and len(binds)==1
    assert result['source_verification']['title']==row['title']


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


@pytest.mark.parametrize('launched,identity', [(False,'original'),(True,'other')])
def test_notice_requires_exact_successful_entry(tmp_path,launched,identity):
    entry=tmp_path/'entry.json'
    entry.write_text(json.dumps(dict(identity=identity,capture_job_id='capture-original',entry_launched=launched)))
    with pytest.raises(EnrichmentError,match='outcome unresolved'):
        human.request_human_action_once(tmp_path/'notice.json',published_at='original session',
            identity='original',capture_job_id='capture-original',entry_receipt=entry)
    assert not (tmp_path/'notice.json').exists()


@pytest.mark.parametrize('capture', [None,dict(status='downloading'),dict(status='awaiting_capture',candidate={'id':'accepted'}),dict(status='awaiting_capture',expected_source={'live_id':'bound'})])
def test_entry_refresh_refuses_capture_effects(monkeypatch,capture):
    driver=object.__new__(XiaocaoLiveCaptureDriver)
    monkeypatch.setattr(driver,'_service',lambda _:SimpleNamespace(capture_store=SimpleNamespace(latest=lambda _:capture)))
    with pytest.raises(EnrichmentError,match='unbound idle capture'):
        driver.require_idle_human_entry('original','capture-original')


@pytest.mark.parametrize("title,published,merchant_title,allowed", [
    ("大师班直播10月29日", "2026-10-29T08:30:00+08:00", "大师班直播10月29日", True),
    ("大师班直播10月28日", "2026-10-29T08:30:00+08:00", "大师班直播10月28日", False),
    ("大师班直播", "2026-10-29T08:30:00+08:00", "大师班直播", False),
    ("大师班直播10月29日", "2026-10-29T16:30:00+08:00", "大师班直播10月29日", False),
    ("大师班直播10月29日", "2026-10-29T08:30:00+08:00", "盘前大师班直播10月29日", False),
])
def test_dated_morning_merchant_title(title, published, merchant_title, allowed):
    started = datetime.fromisoformat("2026-10-29T09:20:00+08:00")
    lineage = {"course_title": merchant_title, "course_start_at": started.timestamp(),
               "metadata_anchors": [{"live_id": "same-live"}]}
    if allowed:
        proof = human.verify_course_metadata({"title": title}, lineage, published)
        assert proof["title"] == title
        assert proof["merchant_title"] == merchant_title
    else:
        with pytest.raises(EnrichmentError):
            human.verify_course_metadata({"title": title}, lineage, published)


@pytest.mark.parametrize('title,merchant_title,published,allowed', [
    ('抽平板电脑｜大师班回馈专场', '抽平板电脑｜大师班回馈专场', '2026-10-30T16:52:00+08:00', True),
    ('抽平板电脑 | 大师班回馈专场', '抽平板电脑｜大师班回馈专场', '2026-10-30T16:52:00+08:00', True),
    ('抽平板电脑｜大师班回馈专场', '大师班专场', '2026-10-30T16:52:00+08:00', False),
    ('抽手机｜大师班回馈专场', '抽手机｜大师班回馈专场', '2026-10-30T16:52:00+08:00', False),
    ('抽平板电脑｜大师班回馈专场', '抽平板电脑｜大师班回馈专场', '2026-10-29T16:52:00+08:00', False),
    ('抽平板电脑｜大师班回馈专场', '抽平板电脑｜大师班回馈专场', '2026-10-30T08:35:00+08:00', False),
])
def test_exact_evening_feedback_course(title, merchant_title, published, allowed):
    lineage = {'course_title': merchant_title, 'course_start_at': 1793354400,
               'metadata_anchors': [{'live_id': 'same-live'}]}
    if allowed:
        proof = human.verify_course_metadata({'title': title}, lineage, published)
        assert proof['title'] == title
        assert proof['merchant_title'] == merchant_title
    else:
        with pytest.raises(EnrichmentError):
            human.verify_course_metadata({'title': title}, lineage, published)
