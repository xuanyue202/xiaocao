from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from xiaocao.kol.replay_catalog import (
    ReplayCatalogConfig, ReplayCatalogError, ReplayCatalogReader, inspect_original,
    verify_original,
)


CONFIG = ReplayCatalogConfig('appTest123', 'course_Example123', 'Token123')
NOW = datetime(2026, 11, 4, 15, tzinfo=ZoneInfo('Asia/Shanghai'))
ITEM = dict(identity='kol-wechat-'+'a'*24, message_sha256='b'*64,
            mini_program_token='Token123', published_at='2026-11-04T09:04:00+08:00',
            capture_job_id='kol-original')


def row(number=1, title='大师班早盘直播11月4日'):
    resource = f'v_{number:024x}'
    return dict(course_id=CONFIG.course_id, chapter_id=resource, chapter_title=title,
                resource_type=3, video_length=2311, jump_url='/p/course/video/'+resource)


class Response:
    status_code = 200
    headers = {}

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Session:
    def __init__(self, pages, detail=None):
        self.pages = iter(pages)
        self.detail = detail
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(('get', url))
        return Response(None)

    def post(self, url, **kwargs):
        self.calls.append(('post', url))
        return Response(self.detail if 'detail_info' in url else next(self.pages))


def page(rows, total=None):
    return dict(code=0, data=dict(total=len(rows) if total is None else total,
                                 list=rows, has_chapter=False))


def test_mixed_live_catalogue_keeps_unrelated_recording_but_blocks_same_day():
    from xiaocao.kol.replay_catalog import match_original
    live_id = 'l_' + 'a' * 24
    live = dict(course_id=CONFIG.course_id, chapter_id=live_id,
                chapter_title='11月27日复盘大师班直播YJ', resource_type=4,
                video_length=None, jump_url='/v4/course/alive/' + live_id + '?type=2')
    rows = ReplayCatalogReader(CONFIG, session=Session([page([row(), live])])).read()
    assert match_original(rows, ITEM['published_at'])['resource_id'] == row()['chapter_id']
    with pytest.raises(ReplayCatalogError, match='recorded_session_live_entry_requires_inspection'):
        match_original(rows, '2026-11-27T17:00:00+08:00')
    live['jump_url'] = 'https://foreign.example/v4/course/alive/' + live_id
    with pytest.raises(ReplayCatalogError, match='catalog_resource_binding_invalid'):
        ReplayCatalogReader(CONFIG, session=Session([page([row(), live])])).read()
    live['jump_url'] = 'https://[malformed'
    with pytest.raises(ReplayCatalogError, match='catalog_resource_binding_invalid'):
        ReplayCatalogReader(CONFIG, session=Session([page([row(), live])])).read()


def test_dated_recap_title_without_expected_wording_needs_review():
    from xiaocao.kol.replay_catalog import match_original
    candidate = {'resource_id': 'v_' + 'b' * 24, 'title': '11月25日复盘直播',
                 'duration_seconds': 2611}
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        match_original([candidate], '2026-11-25T17:22:00+08:00')


def test_manual_recording_authorization_binds_only_exact_original_and_resource():
    from xiaocao.kol.replay_catalog import select_original_recordings, verify_catalogue_binding
    item = {**ITEM, 'published_at':'2026-11-25T17:22:00+08:00',
            'manual_backfill_since':'2026-11-25', 'mini_program_token':'rotated'}
    original = {**item, 'mini_program_name':'见势擒龙团', 'contact':'contact', 'contact_username':'user'}
    item.update(mini_program_name='见势擒龙团', contact='contact', contact_username='user')
    auth = {k:item[k] for k in ('identity','capture_job_id','message_sha256','published_at')}
    auth.update(scope='one_original_recording',user_authorized=True,approval_reference='call_test123',
                authorized_at='2026-11-28T22:15:00+08:00',app_id=CONFIG.app_id,
                course_id=CONFIG.course_id,resource_id='v_'+'b'*24,
                title='11月25日复盘直播',file_name='11月25日复盘剪辑',duration_seconds=2611)
    item['manual_recorded_catalogue_authorization'] = auth
    selected = {'resource_id':auth['resource_id'],'title':auth['title'],
                'duration_seconds':2611,'course_id':CONFIG.course_id}
    verify_catalogue_binding(CONFIG,item,[original])
    assert select_original_recordings([selected],item) == [selected]
    saved_row = {**row(2, auth['title']), 'chapter_id':auth['resource_id'],
                 'video_length':2611, 'jump_url':'/p/course/video/'+auth['resource_id']}
    result = inspect_original(CONFIG,item,originals=[original],session=Session([page([saved_row])]),
                              now=datetime(2026,11,29,8,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert result['recording']['resource_id'] == auth['resource_id']
    for changed in ({**auth,'user_authorized':False}, {**auth,'message_sha256':'c'*64},
                    {**auth,'capture_job_id':'kol-other'}, {**auth,'app_id':'appOther'}):
        with pytest.raises(ReplayCatalogError, match='manual_recorded_authorization_invalid'):
            verify_catalogue_binding(CONFIG,{**item,'manual_recorded_catalogue_authorization':changed},[original])
    with pytest.raises(ReplayCatalogError, match='manual_recorded_resource_changed'):
        select_original_recordings([{**selected,'duration_seconds':2612}],item)
    with pytest.raises(ReplayCatalogError, match='manual_recorded_resource_changed'):
        select_original_recordings([selected,selected],item)
    with pytest.raises(ReplayCatalogError, match='manual_recorded_session_ambiguous'):
        select_original_recordings([selected,{**selected,'resource_id':'v_'+'c'*24,
                                    'title':'11月25日复盘直播片段2'}],item)
    with pytest.raises(ReplayCatalogError, match='original_outside_current_recovery_window'):
        inspect_original(CONFIG,{**ITEM,'published_at':'2026-11-25T17:22:00+08:00'},
                         now=datetime(2026,11,29,8,tzinfo=ZoneInfo('Asia/Shanghai')))


def test_exact_recording_found_without_new_capture_or_ticket_export():
    detail = dict(code=0, data=dict(is_available=1, is_free=0, is_subscribe=0,
        is_try=0, is_unlock=0, video_urls='SECRET_SIGNED_TICKET', user_id='private',
        video_info=dict(resource_id=row()['chapter_id'], video_length=2311,
                        is_drm=1, play_sign='SECRET_PLAY_SIGN')))
    session = Session([page([row(), row(2, '大师班复盘直播11月4日')])], detail)
    result = inspect_original(CONFIG, ITEM, session=session, now=NOW, inspect_access=True)
    assert result['capture_job_id'] == 'kol-original'
    assert result['recording']['resource_id'] == row()['chapter_id']
    assert result['recording']['duration_seconds'] == 2311
    assert result['access']['is_subscribe'] == 0
    assert result['access']['is_drm'] == 1
    assert result['session_verified'] is False
    assert result['download_attempted'] is False
    assert 'SECRET' not in str(result) and 'private' not in str(result)
    assert len(session.calls) == 3


@pytest.mark.parametrize('rows,code', [
    ([row(1), row(2)], 'recorded_session_ambiguous'),
    ([{**row(), 'course_id':'course_Other'}], 'catalog_resource_binding_invalid'),
    ([{**row(), 'jump_url':'https://other.example/video'}], 'catalog_resource_binding_invalid'),
    ([{**row(), 'video_length':True}], 'catalog_resource_binding_invalid'),
])
def test_ambiguous_or_misbound_resource_fails_closed(rows, code):
    with pytest.raises(ReplayCatalogError, match=code):
        inspect_original(CONFIG, ITEM, session=Session([page(rows)]), now=NOW)


def test_no_same_session_match_is_not_media_unavailable_or_completion():
    result = inspect_original(CONFIG, ITEM, now=NOW,
        session=Session([page([row(1, '大师班复盘直播11月4日'),row(2,'大师班早盘直播11月3日')])]))
    assert result['status'] == 'recorded_replay_not_listed'
    assert result['recording'] is None and result['download_attempted'] is False


def test_exact_session_title_order_is_supported_but_intraday_is_not_guessed():
    result = inspect_original(CONFIG, ITEM, now=NOW,
        session=Session([page([row(1, '11月4日早盘大师班直播')])]))
    assert result['recording']['resource_id'] == row()['chapter_id']
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        inspect_original(CONFIG, ITEM, now=NOW,
            session=Session([page([row(1, '11月4日盘中大师班直播')])]))
    result = inspect_original(CONFIG, ITEM, now=NOW,
        session=Session([page([row(1, '11月4日大师班会员说明')])]))
    assert result['recording'] is None


def test_dated_unfamiliar_session_with_suffix_is_not_unpublished():
    item = {**ITEM, 'published_at': '2026-11-23T09:17:00+08:00'}
    rows = [row(1, '11月23日盘前大师班直播YJ(35)-2026-11-23 10:27:29'),
            row(2, '11月23日复盘大师班直播')]
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        inspect_original(CONFIG, item, now=NOW.replace(month=11, day=24, hour=11),
                         session=Session([page(rows)]))


def test_exact_preopen_source_session_and_recording_time_are_required():
    from xiaocao.kol.replay_catalog import match_original
    item_time = '2026-11-23T09:17:00+08:00'
    anchor = '2026-11-23T09:20:00+08:00'
    title = '11月23日盘前大师班直播YJ(35)-2026-11-23 10:27:29'
    candidate = {'resource_id': 'v_'+'a'*24, 'title': title, 'duration_seconds': 3988}
    assert match_original([candidate], item_time, preopen_start_at=anchor) == candidate
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        match_original([candidate], item_time)
    for changed in (
        {**candidate,'title':title.replace('盘前','盘中')},
        {**candidate,'title':title.replace('2026-11-23','2026-11-22')},
        {**candidate,'duration_seconds': 2000},
    ):
        with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
            match_original([changed], item_time, preopen_start_at=anchor)
    with pytest.raises(ReplayCatalogError, match='recorded_session_ambiguous'):
        match_original([candidate,{**candidate,'resource_id':'v_'+'b'*24}],item_time,preopen_start_at=anchor)
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        match_original([candidate],item_time,preopen_start_at='2026-11-23T09:20:00')
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        match_original([candidate],'2026-11-23T16:17:00+08:00',preopen_start_at=anchor)


def test_preopen_catalogue_uses_fresh_original_not_a_claimed_anchor():
    from xiaocao.kol.xiaocao_wechat import parse_xiaocao_live_messages
    text = ("[2026-11-23 09:17] test-contact: ⏰企业微信app课程已发送，09：20和草神一起看\n"
            "1⃣盘前早盘+晚盘【密码666】：#小程序://见势擒龙团/Token123")
    history = {'chat':'test-contact','username':'exact','messages':[text]}
    original = parse_xiaocao_live_messages(history)[0]
    item = {k:v for k,v in original.items() if k != 'recorded_preopen_start_at'}
    item['capture_job_id'] = 'kol-original'
    target = row(1,'11月23日盘前大师班直播YJ(35)-2026-11-23 10:27:29')
    target['video_length'] = 3988
    result = inspect_original(CONFIG,item,originals=[original],
                              now=NOW.replace(month=11,day=24,hour=11),session=Session([page([target])]))
    assert result['recording']['resource_id'] == target['chapter_id']
    # An item-supplied claim cannot stand in for freshly parsed source evidence.
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        inspect_original(CONFIG,{**item,'recorded_preopen_start_at':'2026-11-23T09:20:00+08:00'},
                         originals=[{k:v for k,v in original.items() if k != 'recorded_preopen_start_at'}],
                         now=NOW.replace(month=11,day=24,hour=11),session=Session([page([target])]))


def test_exact_title_does_not_hide_an_unfamiliar_same_day_candidate():
    rows = [row(1, '11月4日早盘大师班直播'),
            row(2, '11月4日盘前大师班直播YJ(35)-2026-11-04 10:27:29')]
    with pytest.raises(ReplayCatalogError, match='recorded_session_title_unverified'):
        inspect_original(CONFIG, ITEM, now=NOW, session=Session([page(rows)]))


def test_multipart_recording_is_an_agent_repair_not_unpublished_or_one_part_acceptance():
    item = {**ITEM, 'published_at':'2026-11-04T17:00:00+08:00'}
    now = NOW.replace(hour=22)
    with pytest.raises(ReplayCatalogError, match='recorded_course_multipart_requires_assembly'):
        inspect_original(CONFIG, item, now=now, session=Session([page([
            row(1, '11月4日复盘大师班直播片段1'),
            row(2, '11月4日复盘大师班直播片段2'),
        ])]))
    with pytest.raises(ReplayCatalogError, match='recorded_course_multipart_requires_assembly'):
        inspect_original(CONFIG, item, now=now, session=Session([page([
            row(1, '11月4日复盘大师班直播'),
            row(2, '11月4日复盘大师班直播片段2'),
        ])]))


def test_complete_pagination_and_total_changes():
    first = [row(i, '11月3日大师班早盘直播') for i in range(1,51)]
    reader = ReplayCatalogReader(CONFIG, session=Session([page(first,51),page([row(51)],51)]))
    assert len(reader.read()) == 51
    bad_pages = [page(first,51),page([row(51)],52)]
    with pytest.raises(ReplayCatalogError, match='catalog_scan_incomplete'):
        ReplayCatalogReader(CONFIG, session=Session(bad_pages)).read()
    with pytest.raises(ReplayCatalogError, match='catalog_scan_incomplete'):
        ReplayCatalogReader(CONFIG, session=Session([page([row()],2)])).read()


@pytest.mark.parametrize('changes', [dict(mini_program_token='Other'),
    dict(published_at='2025-11-04T09:04:00+08:00'),
    dict(published_at='2026-11-05T09:04:00+08:00')])
def test_wrong_source_or_old_year_is_rejected_before_http(changes):
    session = Session([])
    with pytest.raises(ReplayCatalogError):
        inspect_original(CONFIG, {**ITEM, **changes}, session=session, now=NOW)
    assert session.calls == []


def test_redirect_cannot_move_to_another_origin():
    session = Session([])
    response = Response(None)
    response.status_code = 302
    response.headers = {'Location':'https://other.example/'}
    session.get = lambda *a, **k: response
    with pytest.raises(ReplayCatalogError, match='catalog_page_redirect_changed'):
        ReplayCatalogReader(CONFIG, session=session).read()


def test_production_reader_does_not_use_environment_netrc(tmp_path, monkeypatch):
    import requests
    from urllib.parse import urlsplit
    netrc = tmp_path/'netrc'
    netrc.write_text(f'machine {urlsplit(CONFIG.origin).hostname} login secret password secret\n')
    monkeypatch.setenv('NETRC', str(netrc))
    with requests.Session() as vulnerable:
        assert 'Authorization' in vulnerable.prepare_request(
            requests.Request('GET', CONFIG.page_url)).headers
    reader = ReplayCatalogReader(CONFIG)
    try:
        request = reader.session.prepare_request(requests.Request('GET', CONFIG.page_url))
        assert 'Authorization' not in request.headers
    finally:
        reader.session.close()


@pytest.mark.parametrize('changes', [dict(identity='kol-wechat-'+'c'*24),
    dict(message_sha256='c'*64),dict(published_at='2026-11-03T09:04:00+08:00')])
def test_manifest_must_match_requested_cached_original(changes):
    with pytest.raises(ReplayCatalogError):
        verify_original({**ITEM, **changes}, ITEM['identity'], [ITEM])
    verify_original(ITEM, ITEM['identity'], [ITEM])


def test_cli_rejects_manifest_key_identity_mismatch_before_history_or_http(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1]/'scripts/kol_replay_catalog.py'
    spec = importlib.util.spec_from_file_location('catalog_cli_test', path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    subscription = tmp_path/'subscription'
    subscription.mkdir()
    (tmp_path/'native_share_bridge.json').write_text(json.dumps({'replay_catalog':
        dict(app_id=CONFIG.app_id,course_id=CONFIG.course_id,mini_program_token=CONFIG.mini_program_token)}))
    (subscription/'manifest.json').write_text(json.dumps({'items':{
        ITEM['identity']:{**ITEM,'identity':'kol-wechat-'+'c'*24}}}))
    monkeypatch.setattr('sys.argv',['kol_replay_catalog.py','--identity',ITEM['identity'],
                                 '--subscription-dir',str(subscription)])
    monkeypatch.setattr(cli,'WechatCliHistoryReader',lambda:pytest.fail('must stop before history'))
    monkeypatch.setattr(cli,'inspect_original',lambda *a,**k:pytest.fail('must stop before HTTP'))
    assert cli.main() == 2
    assert json.loads(capsys.readouterr().out)['code'] == 'original_identity_changed'


def test_changed_share_token_requires_exact_same_message_catalogue_anchor():
    config = ReplayCatalogConfig(
        CONFIG.app_id, CONFIG.course_id, CONFIG.mini_program_token,
        navigation_source_url='https://yv9lc.xetslk.com/s/4uRHyc',
    )
    item = {**ITEM, 'mini_program_name': '见势擒龙团',
            'entry_kind': 'wechat_mini_program', 'mini_program_token': 'Changed123',
            'contact': 'registered', 'contact_username': 'exact'}
    navigation = {**item, 'identity': 'kol-wechat-'+'c'*24,
                  'entry_kind': None, 'mini_program_token': None,
                  'source_url': config.navigation_source_url,
                  'recorded_navigation_marker': True,
                  'recorded_navigation_url_sha256': __import__('hashlib').sha256(
                      config.navigation_source_url.encode()).hexdigest()}
    session = Session([page([row()])])
    result = inspect_original(config, item, originals=[item, navigation],
                              session=session, now=NOW)
    assert result['recording']['resource_id'] == row()['chapter_id']
    assert item['mini_program_token'] == 'Changed123'
    for field, value in (
        ('message_sha256', 'd'*64), ('published_at', '2026-11-03T09:04:00+08:00'),
        ('contact_username', 'another'), ('source_url', 'https://other.example/'),
        ('recorded_navigation_marker', False),
        ('recorded_navigation_url_sha256', 'd'*64),
    ):
        rejected = Session([])
        with pytest.raises(ReplayCatalogError):
            inspect_original(config, item,
                originals=[item, {**navigation, field: value}],
                session=rejected, now=NOW)
        assert rejected.calls == []
    with pytest.raises(ReplayCatalogError):
        inspect_original(config, item, originals=[item, navigation,
            {**item, 'identity':'kol-wechat-'+'d'*24}], session=Session([]), now=NOW)


def test_evening_original_excludes_dated_preopen_but_rejects_mixed_sessions():
    from xiaocao.kol.replay_catalog import match_original
    published='2026-11-17T16:27:00+08:00'
    morning={'title':'11月17日盘前大师班直播','resource_id':'v_'+'a'*24,'duration_seconds':3116}
    evening={'title':'11月17日复盘大师班直播','resource_id':'v_'+'b'*24,'duration_seconds':4215}
    assert match_original([morning,evening],published)==evening
    with pytest.raises(ReplayCatalogError,match='recorded_session_title_unverified'):
        match_original([evening,{**morning,'title':'11月17日盘前复盘大师班直播'}],published)
    with pytest.raises(ReplayCatalogError,match='recorded_session_title_unverified'):
        match_original([evening,{**morning,'title':'11月17日盘中大师班直播'}],published)
    with pytest.raises(ReplayCatalogError,match='recorded_session_title_unverified'):
        match_original([morning],'2026-11-17T09:17:00+08:00')
