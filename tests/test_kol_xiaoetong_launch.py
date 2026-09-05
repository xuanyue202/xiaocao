import base64
import json
from urllib.parse import urlencode

import pytest

from xiaocao.kol.xiaoetong_launch import (
    LaunchResolutionError, _trusted_url, parse_launch_page, resolve_launch_plan,
)


PAGE = "https://app123.h5.xiaoeknow.com/v2/course/alive/l_target?app_id=app123&alive_mode=0"
IDENTITY = "xiaoetong:app123:l_target"
LINK = "https://wxmpurl.cn/real-ticket"


def encoded(value):
    return base64.b64encode(value.encode()).decode()


def launch_html(page=PAGE, live_id="l_target"):
    query = urlencode({"params": encoded(json.dumps({"pageUrl": page, "alive_id": live_id}))})
    return """if (mock) { window.data = { url_scheme: 'weixin://mock' } } else {
      window.data = {
        nickname: '鹅直播',
        url_scheme: 'weixin://dl/business/?t=real-ticket',
        user_name: 'gh_363391d02e3e',
        path: '/pages/webView/webView',
        //query: 'incorrect commented value',
        query: base64Decode('%s')
      }
    }""" % encoded(query)


def test_real_ticket_ignores_mock_and_is_not_playback_proof():
    plan = parse_launch_page(launch_html(), LINK, IDENTITY)
    assert plan["launch_command"] == ["/usr/bin/open", "-b", "com.tencent.xinWeChat", "weixin://dl/business/?t=real-ticket"]
    assert plan["source_identity"] == IDENTITY
    assert plan["page_state"] == "unknown"
    assert plan["media_request_observed"] is False


@pytest.mark.parametrize("html,link,identity", [
    (launch_html(live_id="l_other"), LINK, IDENTITY),
    (launch_html(), LINK, "xiaoetong:app123:l_other"),
    (launch_html(), "https://wxmpurl.cn/wrong", IDENTITY),
    (launch_html().replace("/pages/webView/webView", "/other"), LINK, IDENTITY),
    (launch_html().replace("base64Decode", "unknownDecode"), LINK, IDENTITY),
])
def test_unproven_launch_is_rejected(html, link, identity):
    with pytest.raises(LaunchResolutionError):
        parse_launch_page(html, link, identity)


def test_read_only_resolver_validates_source_before_launch():
    source_url = "https://share.xet.tech/s/source"
    wrapper = "https://app123.mp.xiaoeknow.com/?" + urlencode({
        "app_id": "app123", "params": encoded(json.dumps({
            "app_id": "app123", "resource_id": "l_target", "h5_url": PAGE,
        })),
    })
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return wrapper, ""
        if len(calls) == 2:
            assert "get_elive_outside_url?" in url
            return url, json.dumps({"code": 0, "data": {"type": 0, "url": LINK}})
        return LINK, launch_html()

    assert resolve_launch_plan(source_url, expected_identity=IDENTITY, fetch=fetch)["live_id"] == "l_target"
    assert len(calls) == 3


def test_bound_h5_anchor_is_not_opened_as_a_playback_page():
    calls = []

    def fetch(url):
        calls.append(url)
        assert url != PAGE
        if "get_elive_outside_url?" in url:
            return url, json.dumps({"code": 0, "data": {"type": 0, "url": LINK}})
        return LINK, launch_html()

    assert resolve_launch_plan(PAGE, expected_identity=IDENTITY, fetch=fetch)["live_id"] == "l_target"
    assert len(calls) == 2


@pytest.mark.parametrize("url", ["http://wxmpurl.cn/a", "https://127.0.0.1/a", "https://xiaoeknow.com.evil.test/a", "https://u:p@wxmpurl.cn/a"])
def test_resolver_rejects_untrusted_redirects(url):
    with pytest.raises(LaunchResolutionError):
        _trusted_url(url)
