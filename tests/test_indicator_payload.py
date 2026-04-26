from __future__ import annotations

from typing import Any

import pytest

from xiaocao.api.client import XiaocaoClient


class _RecordingClient(XiaocaoClient):
    """A XiaocaoClient that captures the path + payload sent to _post_json."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        self.calls.append((path, payload))
        # Return a minimal valid shape so the wrapper's normalizer doesn't blow up.
        return []


def test_get_technical_index_uses_raw_body() -> None:
    client = _RecordingClient()
    client.get_technical_index(stock_ids="300750.XSHE", indicator="smallGrass")
    path, payload = client.calls[-1]
    assert path == "/stock/get_technical_index"
    # Raw body: keys appear at top-level, NOT wrapped under {"params": ...}.
    assert "params" not in payload
    assert payload["indicators"] == "smallGrass"
    assert payload["code"] == "300750.XSHE"


def test_get_technical_index_history_uses_raw_body_with_defaults() -> None:
    client = _RecordingClient()
    client.get_technical_index_history(
        stock_id="300750.XSHE",
        freq="D",
        indicator="smallGrass",
        count=120,
        adj="qfq",
    )
    path, payload = client.calls[-1]
    assert path == "/stock/get_technical_index_history"
    assert "params" not in payload
    assert payload == {
        "freq": "D",
        "adj": "qfq",
        "count": 120,
        "indicators": "smallGrass",
        "code": "300750.XSHE",
    }


def test_get_technical_index_accepts_multiple_codes_csv() -> None:
    client = _RecordingClient()
    client.get_technical_index(stock_ids=["300750.XSHE", "000001.XSHE"], indicator="smallGrass")
    _, payload = client.calls[-1]
    assert payload["code"] == "300750.XSHE,000001.XSHE"


@pytest.mark.parametrize("indicator", ["smallGrass", "vol", "amt", "macd", "rsi", "kdj", "boll"])
def test_get_technical_index_accepts_all_backend_indicators(indicator: str) -> None:
    client = _RecordingClient()
    client.get_technical_index(stock_ids="X", indicator=indicator)
    _, payload = client.calls[-1]
    assert payload["indicators"] == indicator
