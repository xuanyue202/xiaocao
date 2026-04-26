"""Test client.minute_line wrapper — historical playback param plumbing."""
from __future__ import annotations

from typing import Any

from xiaocao.api.client import XiaocaoClient


class _StubClient(XiaocaoClient):
    """Capture the (path, payload) of the last post() call without HTTP."""

    def __init__(self) -> None:
        self.last_path: str | None = None
        self.last_payload: dict[str, Any] | None = None
        self.cache = None
        self.base_url = ""
        self.timeout = 10.0
        self.retries = 0

    def post(self, path: str, params: dict[str, Any]) -> Any:  # type: ignore[override]
        self.last_path = path
        self.last_payload = params
        return []


def test_minute_line_default_today_no_count() -> None:
    """Without count, payload should NOT include count → backend treats as 'live today'."""
    c = _StubClient()
    c.minute_line("002347.XSHE")
    assert c.last_path == "/stock/minute_line"
    assert c.last_payload is not None
    assert "count" not in c.last_payload
    assert "tradeDate" not in c.last_payload
    assert c.last_payload["adj"] == "bfq"
    assert c.last_payload["freq"] == "1min"
    assert c.last_payload["code"] == "002347.XSHE"
    assert c.last_payload["codeType"] == 0


def test_minute_line_history_passes_trade_date_and_count() -> None:
    """With trade_date + count: payload includes both, backend honors history."""
    c = _StubClient()
    c.minute_line("002347.XSHE", trade_date="2026-04-22", count=241)
    assert c.last_payload is not None
    assert c.last_payload["tradeDate"] == "20260422"
    assert c.last_payload["count"] == 241
    assert c.last_payload["code"] == "002347.XSHE"


def test_minute_line_xchjzs_routes_to_env_endpoint() -> None:
    """code with .XCHJZS suffix routes to xiao_cao_environment_minute_line and strips suffix."""
    c = _StubClient()
    c.minute_line("9A0001.XCHJZS", trade_date="2026-04-22", count=241)
    assert c.last_path == "/stock/xiao_cao_environment_minute_line"
    assert c.last_payload is not None
    assert c.last_payload["code"] == "9A0001"  # suffix stripped per JS K0 wrapper


def test_minute_line_compact_date_format_yyyymmdd() -> None:
    """Either YYYY-MM-DD or YYYYMMDD input is normalized to YYYYMMDD on the wire."""
    c = _StubClient()
    c.minute_line("X.XSHE", trade_date="20260422", count=10)
    assert c.last_payload is not None
    assert c.last_payload["tradeDate"] == "20260422"

    c2 = _StubClient()
    c2.minute_line("X.XSHE", trade_date="2026-04-22", count=10)
    assert c2.last_payload is not None
    assert c2.last_payload["tradeDate"] == "20260422"
