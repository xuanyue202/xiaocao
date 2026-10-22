"""Native replay reader, ported from independently verified d90f9cde.

No media endpoints, cookies or decoding keys are persisted by evidence().
"""
import hashlib, json, math, os, re, time, urllib.error, urllib.parse, urllib.request
PROTECTION_WORDS = ('captcha', '验证码', '频繁', '登录', 'login', 'protect', '风控')
class CaptureError(RuntimeError):
    """Only constant, credential-free categories may cross the evidence boundary."""

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def check_error(code, message, category):
    text = str(message).lower()
    if code != 0:
        if any(word in text for word in PROTECTION_WORDS):
            raise CaptureError('access_protection')
        if 'timed out' in text or 'timeout' in text:
            raise CaptureError('request_timeout')
        raise CaptureError(category)

def request(api, route, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(api + route, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 429):
            raise CaptureError('access_protection') from None
        raise CaptureError('transport_unknown_result' if payload is not None and error.code >= 500 else 'candidate_http_error') from None
    except (TimeoutError, urllib.error.URLError) as error:
        is_timeout = isinstance(error, TimeoutError) or isinstance(getattr(error, 'reason', None), TimeoutError)
        raise CaptureError('transport_unknown_result' if payload is not None else 'request_timeout' if is_timeout else 'transport_error') from None
    check_error(result.get('code'), result.get('msg'), 'candidate_api_error')
    return result.get('data') or {}

def save(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as handle:
        os.chmod(tmp, 0o600)
        json.dump(data, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)

def finite_duration(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0

def evidence(obj):
    replay_id = str(obj.get('id') or '')
    created = obj.get('createtime')
    if not re.fullmatch(r'[0-9]+', replay_id) or type(created) is not int or created <= 0:
        raise CaptureError('invalid_replay_identity_time')
    media = (obj.get('objectDesc') or {}).get('media') or []
    first = media[0] if media else {}
    return {
        'replay_id': replay_id, 'publisher_sha256': digest(obj.get('username') or ''),
        'created_at': created,
        'title': re.sub(r'https?://\S+', '[link]', (obj.get('objectDesc') or {}).get('description') or '')[:200],
        'duration_seconds': first.get('videoPlayLen'), 'native_source_size': first.get('fileSize'),
        'width': first.get('width'), 'height': first.get('height'),
        'variant_specs': [{k: s.get(k) for k in ('fileFormat', 'fileSize', 'width', 'height', 'bitRate') if k in s}
                          for s in first.get('spec') or []],
        'media_url_observed': bool(first.get('url')), 'source_live_id_verified': False,
    }

def replay_page(api, username, marker):
    reply = request(api, '/api/channels/live/replay/list?' + urllib.parse.urlencode({'username': username, 'next_marker': marker}))
    check_error(reply.get('errCode'), reply.get('errMsg'), 'native_api_error')
    data = reply.get('data') or {}
    base = data.get('BaseResponse') or {}
    check_error(base.get('Ret', 0), base.get('ErrMsg'), 'native_base_error')
    contact = (data.get('contact') or {}).get('username')
    if contact and contact != username:
        raise CaptureError('publisher_contact_mismatch')
    for obj in data.get('object') or []:
        if obj.get('username') != username:
            raise CaptureError('replay_publisher_mismatch')
        evidence(obj)
    return data

def publisher_objects(api, username, max_pages, interval, progress):
    marker = ''; seen = set(); objects = {}
    for _ in range(max_pages):
        data = replay_page(api, username, marker)
        rows = data.get('object') or []
        for obj in rows:
            replay_id = str(obj['id'])
            if replay_id in objects and evidence(objects[replay_id]) != evidence(obj):
                raise CaptureError('replay_identity_changed')
            objects[replay_id] = obj
        progress['pages'] += 1
        if not data.get('continueFlag'):
            if not (data.get('contact') or {}).get('username') and not objects:
                raise CaptureError('empty_publisher_identity_unverified')
            return objects
        marker = data.get('lastBuffer') or ''
        if not marker or digest(marker) in seen:
            raise CaptureError('pagination_stalled')
        seen.add(digest(marker)); time.sleep(interval)
    raise CaptureError('pagination_limit')

def fetch_selected(api, username, record, max_pages, interval):
    # Fresh native identity and finite media are required even after catalog resume.
    objects = publisher_objects(api, username, max_pages, interval, {'pages': 0})
    obj = objects.get(record['replay_id'])
    if obj is None:
        raise CaptureError('selected_replay_missing')
    fresh = evidence(obj)
    for key in ('replay_id', 'publisher_sha256', 'created_at', 'duration_seconds'):
        if fresh[key] != record[key]:
            raise CaptureError('selected_replay_binding_changed')
    if not fresh['media_url_observed'] or not finite_duration(fresh['duration_seconds']):
        raise CaptureError('selected_media_unverified')
    return obj
