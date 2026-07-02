from __future__ import annotations

from xiaocao.strategy.trend_rules import generate_trend_picks


class FakeTrendClient:
    def stock_info(self):
        return [
            {"code": "000AAA.XSHE", "codeName": "小票A", "statusType": 1, "tradableAShare": 100},
            {"code": "600BIG.XSHG", "codeName": "大票B", "statusType": 1, "tradableAShare": 10_000},
            {"code": "600MID.XSHG", "codeName": "大票C", "statusType": 1, "tradableAShare": 8_000},
            {"code": "000IDX.XSHG", "codeName": "指数", "statusType": 99, "tradableAShare": 99_999},
        ]

    def get_block_category_rank_v3(self, date, model=0):
        return [
            {"categoryCode": "C2.BKDL", "name": "后排", "num": 50},
            {"categoryCode": "C1.BKDL", "name": "主线", "num": 200, "trendScore": 188},
        ]

    def get_code_by_xiao_cao_block(self, date, **filters):
        if filters.get("categoryCodeList") == "C1.BKDL":
            return ["000AAA.XSHE", "600BIG.XSHG"]
        if filters.get("categoryCodeList") == "C2.BKDL":
            return ["600MID.XSHG"]
        return []

    def second_line_detail_info(self, codes):
        return {
            "600BIG.XSHG": {
                "code": "600BIG.XSHG",
                "codeName": "大票B",
                "open": 10.0,
                "preClose": 9.9,
                "pctChangeRate": 1.01,
            },
            "600MID.XSHG": {
                "code": "600MID.XSHG",
                "codeName": "大票C",
                "open": 20.0,
                "preClose": 19.8,
                "pctChangeRate": 1.01,
            },
        }


def test_generate_trend_picks_prefers_bigcap_representative():
    picks = generate_trend_picks(FakeTrendClient(), "2026-07-01", max_positions=2)

    assert [p["code"] for p in picks] == ["600BIG.XSHG", "600MID.XSHG"]
    assert picks[0]["book"] == "T"
    assert picks[0]["mode"] == "趋势主线"
    assert picks[0]["is_main_line"] is True
    assert picks[0]["is_big_cap"] is True
    assert picks[0]["category_code"] == "C1.BKDL"
    assert picks[0]["category_rank"] == 1
    assert picks[0]["basket_price"] == 10.08
    assert picks[0]["basket_rule"] == "trend_open+0.8%"
