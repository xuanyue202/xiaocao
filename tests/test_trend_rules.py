from __future__ import annotations

from xiaocao.strategy.trend_rules import classify_trend_alignment, generate_trend_picks


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
    assert picks[0]["trend_alignment"] == "neutral"


class FakePostureClient(FakeTrendClient):
    def stock_info(self):
        return [
            {"code": "601288.XSHG", "codeName": "农业银行", "statusType": 1, "tradableAShare": 300_000},
            {"code": "600000.XSHG", "codeName": "浦发银行", "statusType": 1, "tradableAShare": 200_000},
            {"code": "000725.XSHE", "codeName": "京东方Ａ", "statusType": 1, "tradableAShare": 90_000},
            {"code": "688001.XSHG", "codeName": "电子核心", "statusType": 1, "tradableAShare": 10_000},
            {"code": "003816.XSHE", "codeName": "中国广核", "statusType": 1, "tradableAShare": 80_000},
        ]

    def get_block_category_rank_v3(self, date, model=0):
        return [
            {"categoryCode": "BANK.BKDL", "name": "业绩股权类", "num": 200, "trendScore": 200},
            {"categoryCode": "ELEC.BKDL", "name": "行业电子", "num": 180, "trendScore": 180},
            {"categoryCode": "MID.BKDL", "name": "中市值股票", "num": 170, "trendScore": 170},
        ]

    def get_code_by_xiao_cao_block(self, date, **filters):
        code = filters.get("categoryCodeList")
        if code == "BANK.BKDL":
            return ["601288.XSHG", "600000.XSHG"]
        if code == "ELEC.BKDL":
            return ["000725.XSHE", "688001.XSHG"]
        if code == "MID.BKDL":
            return ["003816.XSHE"]
        return []

    def second_line_detail_info(self, codes):
        return {
            "000725.XSHE": {
                "code": "000725.XSHE",
                "codeName": "京东方Ａ",
                "open": 8.0,
                "preClose": 7.9,
                "pctChangeRate": 1.2,
            },
            "003816.XSHE": {
                "code": "003816.XSHE",
                "codeName": "中国广核",
                "open": 3.8,
                "preClose": 3.79,
                "pctChangeRate": 0.3,
            },
        }


class FakeHiddenBankClient(FakePostureClient):
    def stock_info(self):
        return [
            {"code": "601288.XSHG", "codeName": "", "statusType": 1, "tradableAShare": 300_000},
            {"code": "000725.XSHE", "codeName": "京东方Ａ", "statusType": 1, "tradableAShare": 90_000},
            {"code": "003816.XSHE", "codeName": "中国广核", "statusType": 1, "tradableAShare": 80_000},
        ]

    def get_block_category_rank_v3(self, date, model=0):
        return [
            {"categoryCode": "GENERIC.BKDL", "name": "业绩股权类", "num": 200, "trendScore": 200},
            {"categoryCode": "ELEC.BKDL", "name": "行业电子", "num": 180, "trendScore": 180},
            {"categoryCode": "MID.BKDL", "name": "中市值股票", "num": 170, "trendScore": 170},
        ]

    def get_code_by_xiao_cao_block(self, date, **filters):
        code = filters.get("categoryCodeList")
        if code == "GENERIC.BKDL":
            return ["601288.XSHG"]
        if code == "ELEC.BKDL":
            return ["000725.XSHE"]
        if code == "MID.BKDL":
            return ["003816.XSHE"]
        return []

    def second_line_detail_info(self, codes):
        data = super().second_line_detail_info(codes)
        data["601288.XSHG"] = {
            "code": "601288.XSHG",
            "codeName": "农业银行",
            "open": 6.0,
            "preClose": 5.9,
            "pctChangeRate": 1.7,
        }
        return data


def test_generate_trend_picks_blocks_external_old_direction_and_scans_deeper():
    picks = generate_trend_picks(FakePostureClient(), "2026-07-02", max_positions=2)

    assert [p["code"] for p in picks] == ["000725.XSHE", "003816.XSHE"]
    assert all("银行" not in p["name"] for p in picks)
    assert picks[0]["trend_alignment"] == "aligned"
    assert picks[0]["trend_alignment_reason"] == "小草趋势主线相关:电子"
    assert picks[1]["trend_alignment"] == "neutral"
    assert "兜底" in picks[1]["trend_alignment_reason"]


def test_generate_trend_picks_refills_after_detail_stage_external_filter():
    picks = generate_trend_picks(FakeHiddenBankClient(), "2026-07-02", max_positions=2)

    assert [p["code"] for p in picks] == ["000725.XSHE", "003816.XSHE"]
    assert all(p["code"] != "601288.XSHG" for p in picks)


def test_classify_trend_alignment_marks_external_direction():
    alignment = classify_trend_alignment(name="农业银行", category_name="业绩股权类")

    assert alignment["trend_alignment"] == "external"
    assert "银行" in alignment["trend_alignment_reason"]
