from __future__ import annotations

from xiaocao.datasource.api_source import ApiDataSource


class _OutOfOrderIndexClient:
    def get_xiao_cao_index_v2(self, date: str, codes: list[str], hpqb_state: int, lpdx_state: int):
        return [
            {"code": "C.XSHE", "xcjw": 300},
            {"code": "A.XSHE", "xcjw": 100},
            {"code": "B.XSHE", "xcjw": 200},
        ]


def test_get_stock_index_preserves_requested_code_order() -> None:
    source = ApiDataSource(_OutOfOrderIndexClient())  # type: ignore[arg-type]

    rows = source.get_stock_index("2026-05-18", ["A.XSHE", "B.XSHE", "C.XSHE"])

    assert [row["code"] for row in rows] == ["A.XSHE", "B.XSHE", "C.XSHE"]
