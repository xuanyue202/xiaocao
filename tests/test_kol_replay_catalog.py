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
