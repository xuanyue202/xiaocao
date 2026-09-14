from unittest.mock import MagicMock

import pytest

from xiaocao.api.client import XiaocaoClient
from xiaocao.api.errors import ApiAuthError


def test_expired_upstream_login_is_typed_and_not_retried_or_cached(monkeypatch):
    monkeypatch.setenv("XIAOCAO_API_TOKEN", "")
    client = XiaocaoClient(retries=3, backoff=0, cache=MagicMock())
    client.cache.get.return_value = None
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'code': 990502, 'msg': '登录已失效，请重新登录'}
    client._session.post = MagicMock()
    client._session.post.return_value.__enter__.return_value = response
    with pytest.raises(ApiAuthError, match='990502'):
        client.get_industry_block_rank('2026-09-14', 0)
    assert client._session.post.call_count == 1
    client.cache.put.assert_not_called()
