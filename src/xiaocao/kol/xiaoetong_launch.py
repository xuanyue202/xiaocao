"""Resolve a merchant-issued Goose Live launch ticket without controlling WeChat.

The mobile User-Agent selects the provider's public link representation instead
of its desktop QR representation. It supplies no authentication or entitlement.
Never synthesize a ticket or treat successful resolution as playback evidence.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .capture import InvalidSourcePage, canonical_xiaoetong_source, resolve_xiaoetong_h5_page

_MOBILE_LINK_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
_OUTSIDE_API = "https://service.h5.xiaoeknow.com/_alive/api/get_elive_outside_url"
_SUFFIXES = ("xet.tech", "xiaoeknow.com", "xe-live.com")


class LaunchResolutionError(ValueError):
    """No verified public launch plan is available; use visible UI fallback."""


def _trusted_url(url: str) -> None:
    value = urlsplit(url)
    host = (value.hostname or "").lower()
    if (
        value.scheme != "https"
        or value.username or value.password or value.port not in (None, 443)
        or not (host == "wxmpurl.cn" or any(
            host == suffix or host.endswith("." + suffix) for suffix in _SUFFIXES
        ))
    ):
        raise LaunchResolutionError("untrusted public launch URL")


class _TrustedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _trusted_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str) -> tuple[str, str]:
    _trusted_url(url)
    opener = build_opener(_TrustedRedirects())
    # Preserve the identity-bearing desktop wrapper on the original share hop;
    # request the mobile representation only from the outside-link API.
    user_agent = _MOBILE_LINK_UA if url.startswith(_OUTSIDE_API + "?") else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    request = Request(url, headers={"User-Agent": user_agent})
    with opener.open(request, timeout=15) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise LaunchResolutionError("public launch response is too large")
        _trusted_url(response.url)
        return response.url, body.decode("utf-8")


def _decode(value: str) -> str:
    return base64.b64decode(value + "=" * (-len(value) % 4), validate=True).decode("utf-8")


def parse_launch_page(html: str, web_link: str, expected_identity: str) -> dict:
    # The provider page also contains a mock window.data branch: ignore it.
    match = re.search(r"}\s*else\s*{\s*window\.data\s*=\s*{(.*?)}", html, re.S)
    if not match:
        raise LaunchResolutionError("merchant launch data missing")
    data = match.group(1)

    def field(name: str) -> str:
        found = re.search(r"(?m)^\s*" + name + r":\s*'([^']*)'", data)
        if not found:
            raise LaunchResolutionError("merchant launch field missing")
        return found.group(1)

    encoded = re.search(r"(?m)^\s*query:\s*base64Decode\('([^']+)'\)", data)
    if not encoded:
        raise LaunchResolutionError("merchant launch binding missing")
    try:
        params = parse_qs(_decode(encoded.group(1)), strict_parsing=True)
        payload = json.loads(_decode(params["params"][0]))
        page_url = resolve_xiaoetong_h5_page(payload["pageUrl"])
        source = canonical_xiaoetong_source(page_url)
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise LaunchResolutionError("merchant launch binding invalid") from exc
    scheme = field("url_scheme")
    ticket = re.fullmatch(r"weixin://dl/business/\?t=([A-Za-z0-9_-]{1,128})", scheme)
    link = urlsplit(web_link)
    if (
        not ticket or link.scheme != "https" or link.netloc != "wxmpurl.cn"
        or link.path != "/" + ticket.group(1) or link.query or link.fragment
        or field("nickname") != "鹅直播"
        or field("path") != "/pages/webView/webView"
        or field("user_name") != "gh_363391d02e3e"
        or source["source_identity"] != expected_identity
        or payload.get("alive_id") != source["source_resource_id"]
    ):
        raise LaunchResolutionError("merchant launch target does not match source")
    return {
        "page_url": page_url,
        "source_identity": source["source_identity"],
        "live_id": source["source_resource_id"],
        "web_link": web_link,
        "launch_command": ["/usr/bin/open", "-b", "com.tencent.xinWeChat", scheme],
        "page_state": "unknown",
        "playback_surface": "wechat_mini_program",
        "media_request_observed": False,
    }


def resolve_launch_plan(
    source_url: str, *, expected_identity: str | None = None,
    fetch: Callable[[str], tuple[str, str]] = _fetch,
) -> dict:
    _trusted_url(source_url)
    try:
        # An identity-bearing URL needs no H5 playback/navigation request.
        page_url = resolve_xiaoetong_h5_page(source_url)
    except InvalidSourcePage:
        wrapper, _ = fetch(source_url)
        page_url = resolve_xiaoetong_h5_page(wrapper)
    source = canonical_xiaoetong_source(page_url)
    identity = source["source_identity"]
    if expected_identity is not None and identity != expected_identity:
        raise LaunchResolutionError("source redirect changed the bound session")
    if not source["source_resource_id"].startswith("l_"):
        raise LaunchResolutionError("launch plan supports live replay entries only")
    query = urlencode({
        "app_id": source["source_app_id"],
        "resource_id": source["source_resource_id"],
        "alive_mode": (parse_qs(urlsplit(page_url).query).get("alive_mode") or ["0"])[0],
        "is_anchor": "false", "env_type": "1", "h5_url": page_url,
    })
    _, body = fetch(_OUTSIDE_API + "?" + query)
    result = json.loads(body)
    data = result.get("data") or {}
    if result.get("code") != 0 or data.get("type") != 0:
        raise LaunchResolutionError("provider returned no public launch link")
    web_link = str(data.get("url") or "")
    if not re.fullmatch(r"https://wxmpurl\.cn/[A-Za-z0-9_-]{1,128}", web_link):
        raise LaunchResolutionError("provider launch link unsupported")
    final_link, html = fetch(web_link)
    if final_link != web_link:
        raise LaunchResolutionError("merchant launch page unexpectedly redirected")
    return parse_launch_page(html, web_link, identity)
