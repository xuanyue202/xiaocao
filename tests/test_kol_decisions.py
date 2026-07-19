from __future__ import annotations

import json
from pathlib import Path

import pytest

from xiaocao.kol.decisions import (
    BookKolUs,
    DecisionError,
    DecisionPipeline,
    TranscriptDocument,
)


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _write_household(path: Path) -> Path:
    return _write_text(
        path,
        json.dumps({
            "family_id": "test-family",
            "as_of": "2026-07-19T18:00:00+08:00",
            "source_reference": "test://household",
            "positions": [],
        }),
    )


def _household_context() -> dict:
    return {
        "family_id": "test-family",
        "as_of": "2026-07-19T18:00:00+08:00",
        "source_reference": "test://fresh-household-provider",
        "positions": [],
        "decision_view": {},
    }


def _pipeline(output_dir: Path) -> DecisionPipeline:
    return DecisionPipeline(output_dir, household_context_loader=_household_context)


def _item(path: Path, *, author: str = "小草", ticker: str | None = None) -> dict:
    claim_id = f"{author}-risk"
    paper = (
        {
            "decision": "trade",
            "ticker": ticker,
            "instrument_type": "etf",
            "listing_country": "US",
            "side": "buy",
            "target_weight": 0.35,
            "price": 100.0,
            "concentration_risk": "单一主题集中，波动可能显著高于宽基。",
            "exit_or_falsifier": "市场验证中的失效条件触发。",
        }
        if ticker
        else {"decision": "no_trade", "reason": "观点仅涉及非美股资产。"}
    )
    return {
        "source": "local_transcript",
        "author": author,
        "title": path.stem,
        "published_at": "2026-07-16T17:30:00+08:00",
        "captured_at": "2026-07-19T18:24:00+08:00",
        "evidence_path": str(path),
        "claims": [
            {
                "claim_id": claim_id,
                "quote": "等待成交量放大再行动",
                "reasoning": "缩量下跌未证明风险释放完成。",
                "asset_scope": ["A-share", "macro"],
                "direction": "defensive",
                "horizon": "未来一至两周",
                "confidence": "high",
                "falsifiers": ["放量止跌并形成可交易主线"],
            }
        ],
        "actionable_signals": [
            {
                "signal_id": f"{author}-wait-for-volume",
                "claim_ids": [claim_id],
                "action": "wait",
                "assets": [{"name": "A股短线", "market": "CN", "theme": "oversold"}],
                "relevant_asset_codes": [],
                "horizon": "下一交易周",
                "execution": "放量止跌前不新增短线仓位。",
                "trigger": "低位放量且形成可交易主线。",
                "confidence": "medium",
                "falsifiers": ["放量后继续破位"],
                "rationale": {
                    "news_or_event": [],
                    "fundamental": ["没有新增基本面催化。"],
                    "trading": ["缩量下跌未证明风险释放完成。"],
                },
                "current_validation": {
                    "status": "qualify",
                    "as_of": "2026-07-19T16:00:00+08:00",
                    "summary": "周末无新增交易日，等待下一交易日确认。",
                    "currentness": {
                        "latest_available": True,
                        "checked_at": "2026-07-19T18:00:00+08:00",
                        "reason": "周末无新增交易日。",
                    },
                    "facts": [
                        {
                            "metric": "market_session",
                            "value": "closed",
                            "observed_at": "2026-07-19T16:00:00+08:00",
                            "evidence": "frozen://market/2026-07-19",
                        }
                    ],
                },
            }
        ],
        "market_validation": {
            "status": "qualify",
            "as_of": "2026-07-19T16:00:00+08:00",
            "summary": "周末无新增交易日，保留防守判断并等待下一交易日验证。",
            "currentness": {
                "latest_available": True,
                "checked_at": "2026-07-19T18:00:00+08:00",
                "reason": "周末无新增交易日。",
            },
            "facts": [
                {
                    "metric": "market_session",
                    "value": "closed",
                    "observed_at": "2026-07-19T16:00:00+08:00",
                    "evidence": "frozen://market/2026-07-19",
                }
            ],
        },
        "synthesis": {
            "summary": "系统仅保留等待条件，不把旧观点按日过期。",
            "confidence": "medium",
            "conflicts": [],
        },
        "household_recommendation": {
            "action": "wait",
            "evidence": "缩量风险尚未解除。",
            "confidence": "medium",
            "horizon": "下一交易周",
            "falsifier": "放量止跌且主线确认。",
        },
        "book_kol_us": paper,
    }


def _bundle(item: dict, *, household_path: Path) -> dict:
    return {
        "household_context_provider": {"type": "lianghui_mcp", "fresh_read_per_run": True},
        "items": [item],
        "cross_source": {"agreements": [], "conflicts": []},
    }


def test_transcript_document_reads_plain_text_and_requires_exact_quote(tmp_path):
    path = _write_text(tmp_path / "real.txt", "今天的结论：等待成交量放大再行动。")
    document = TranscriptDocument.load(path)

    assert document.contains("等待成交量放大再行动")
    assert len(document.sha256) == 64
    assert document.text_length > 10


@pytest.mark.parametrize("status", ["support", "qualify", "conflict", "invalidate"])
def test_current_market_validation_accepts_four_explicit_outcomes(tmp_path, status):
    transcript = _write_text(tmp_path / f"{status}.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    item = _item(transcript)
    item["market_validation"]["status"] = status

    result = _pipeline(tmp_path / "out").process(_bundle(item, household_path=household))

    assert result["items"][0]["market_validation"]["status"] == status


def test_pipeline_routes_once_and_keeps_book_isolated(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    bundle = _bundle(_item(transcript, ticker="QQQ"), household_path=household)
    pipeline = _pipeline(tmp_path / "out")

    first = pipeline.process(bundle)
    second = pipeline.process(bundle)

    assert first["items"][0]["notification"]["status"] == "pending"
    assert second["items"][0]["idempotent_replay"] is True
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 1
    assert len((tmp_path / "out" / "book_kol_us" / "trades.jsonl").read_text().splitlines()) == 2
    assert len((tmp_path / "out" / "book_kol_us" / "decisions.jsonl").read_text().splitlines()) == 1
    account = json.loads((tmp_path / "out" / "book_kol_us" / "account.json").read_text())
    assert account["book"] == "KOL-US"
    assert account["cash"] == 65000.0
    decision = json.loads(
        (tmp_path / "out" / "book_kol_us" / "decisions.jsonl").read_text().splitlines()[0]
    )
    assert decision["evidence_context"]["market_validation"]["status"] == "qualify"


def test_rejects_unquoted_claim_and_unsafe_paper_instruments(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "原文没有该说法")
    household = _write_household(tmp_path / "household.json")
    item = _item(transcript, ticker="SPY-PUT")
    item["book_kol_us"]["instrument_type"] = "option"

    with pytest.raises(DecisionError, match="quote not found"):
        _pipeline(tmp_path / "out").process(_bundle(item, household_path=household))

    item["claims"][0]["quote"] = "原文没有该说法"
    with pytest.raises(DecisionError, match="instrument_type"):
        _pipeline(tmp_path / "out").process(_bundle(item, household_path=household))
    assert not (tmp_path / "out" / "household_outbox.jsonl").exists()


def test_framework_only_content_without_actionable_signals_fails_visibly(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript)
    item["actionable_signals"] = []

    result = _pipeline(tmp_path / "out").process(
        _bundle(item, household_path=tmp_path / "unused.json")
    )

    assert result["status"] == "failed"
    assert result["failures"] == ["low_density_content"]


def test_actionable_signal_requires_asset_action_trigger_logic_and_current_validation(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript)
    item["actionable_signals"][0]["assets"] = []

    with pytest.raises(DecisionError, match="actionable signal assets"):
        _pipeline(tmp_path / "out").process(
            _bundle(item, household_path=tmp_path / "unused.json")
        )


def test_off_portfolio_opportunity_survives_household_context_and_gets_funding_context(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript)
    signal = item["actionable_signals"][0]
    signal.update({
        "action": "buy",
        "assets": [{"name": "北特科技", "market": "CN", "ticker": "603009"}],
        "relevant_asset_codes": ["603009"],
        "funding_plan": "由减持杠杆和高拥挤存储仓位腾出资金。",
    })
    item["household_recommendation"]["action"] = "buy"
    item["household_recommendation"]["avoid_add_if_bucket_excess"] = "breakthrough"

    def loader():
        context = _household_context()
        context["decision_view"] = {
            "cashAvailable": 600_000,
            "bucketExcesses": ["breakthrough"],
            "bucketShortfalls": ["foundation"],
        }
        context["positions"] = [{
            "assetName": "三倍做多纳指",
            "assetCode": "TQQQ",
            "assetType": "fund",
            "currency": "USD",
            "currentAmount": 20_000,
            "costConfidence": "full",
        }]
        return context

    result = DecisionPipeline(
        tmp_path / "out", household_context_loader=loader
    ).process(_bundle(item, household_path=tmp_path / "unused.json"))

    result_item = result["items"][0]
    assert result_item["actionable_signals"][0]["action"] == "buy"
    assert result_item["actionable_signals"][0]["context_assessment"]["held"] is False
    assert result_item["household_recommendation"]["action"] == "buy"
    assert "above its target range" in result_item["household_recommendation"]["context_constraint"]


def test_missing_context_market_data_and_ambiguous_ticker_fail_visibly(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript, ticker="UNKNOWN")
    item["market_validation"]["facts"] = []
    item["book_kol_us"]["ticker_ambiguous"] = True

    result = DecisionPipeline(tmp_path / "out").process(
        _bundle(item, household_path=tmp_path / "missing.json")
    )

    assert result["status"] == "failed"
    assert set(result["failures"]) == {
        "missing_household_context",
        "missing_market_data",
        "ambiguous_ticker_mapping",
    }
    assert not (tmp_path / "out" / "household_outbox.jsonl").exists()


def test_cross_source_links_are_judgment_not_votes(tmp_path):
    household = _write_household(tmp_path / "household.json")
    items = []
    for author in ("小草", "吕晓彤", "路西法"):
        transcript = _write_text(tmp_path / f"{author}.txt", "等待成交量放大再行动")
        items.append(_item(transcript, author=author))
    bundle = {
        "household_context_provider": {"type": "lianghui_mcp"},
        "items": items,
        "cross_source": {
            "agreements": [
                {
                    "topic": "risk",
                    "claim_ids": ["小草-risk", "吕晓彤-risk"],
                    "judgment": "都主张保留现金，但理由与资产范围不同。",
                }
            ],
            "conflicts": [
                {
                    "topic": "timing",
                    "claim_ids": ["小草-risk", "路西法-risk"],
                    "judgment": "短线等待与长期配置不是同一时间尺度，不能投票合并。",
                }
            ],
        },
    }

    result = _pipeline(tmp_path / "out").process(bundle)

    assert result["cross_source"]["method"] == "evidence_weighted_judgment"
    assert "vote" not in json.dumps(result["cross_source"], ensure_ascii=False).lower()


def test_no_trade_is_an_idempotent_book_decision(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    bundle = _bundle(_item(transcript), household_path=household)
    pipeline = _pipeline(tmp_path / "out")

    pipeline.process(bundle)
    result = pipeline.process(bundle)

    assert result["items"][0]["book_kol_us"]["idempotent_replay"] is True
    decisions = tmp_path / "out" / "book_kol_us" / "decisions.jsonl"
    assert len(decisions.read_text().splitlines()) == 1


def test_validates_entire_batch_before_any_side_effect(tmp_path):
    household = _write_household(tmp_path / "household.json")
    valid_doc = _write_text(tmp_path / "valid.txt", "等待成交量放大再行动")
    invalid_doc = _write_text(tmp_path / "invalid.txt", "没有对应原话")
    invalid = _item(invalid_doc, author="路西法")
    bundle = {
        "household_context_provider": {"type": "lianghui_mcp"},
        "items": [_item(valid_doc, ticker="QQQ"), invalid],
        "cross_source": {"agreements": [], "conflicts": []},
    }

    with pytest.raises(DecisionError, match="quote not found"):
        _pipeline(tmp_path / "out").process(bundle)

    assert not (tmp_path / "out" / "household_outbox.jsonl").exists()
    assert not (tmp_path / "out" / "book_kol_us" / "account.json").exists()


def test_market_fact_requires_timestamp_and_evidence(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    item = _item(transcript)
    item["market_validation"]["facts"] = [{"metric": "price", "value": 1}]

    with pytest.raises(DecisionError, match="each market fact"):
        _pipeline(tmp_path / "out").process(_bundle(item, household_path=household))

    item["market_validation"]["facts"] = [{
        "metric": "price",
        "value": 1,
        "observed_at": "2026-07-01T16:00:00+08:00",
        "evidence": "frozen://old",
    }]
    item["market_validation"]["currentness"]["checked_at"] = "2026-07-01T18:00:00+08:00"
    with pytest.raises(DecisionError, match="processing time"):
        _pipeline(tmp_path / "out").process(_bundle(item, household_path=household))


def test_paper_trade_recovers_after_crash_between_intent_and_account(tmp_path, monkeypatch):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    bundle = _bundle(_item(transcript, ticker="QQQ"), household_path=household)
    pipeline = _pipeline(tmp_path / "out")

    def crash():
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(pipeline.book, "_persist", crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        pipeline.process(bundle)

    recovered = _pipeline(tmp_path / "out").process(bundle)
    assert recovered["items"][0]["book_kol_us"]["idempotent_replay"] is True
    account = json.loads((tmp_path / "out" / "book_kol_us" / "account.json").read_text())
    assert account["cash"] == 65000.0
    filled = [
        json.loads(line)
        for line in (tmp_path / "out" / "book_kol_us" / "trades.jsonl").read_text().splitlines()
        if json.loads(line).get("event") == "trade_filled"
    ]
    assert len(filled) == 1


def test_notification_delivery_receipt_is_idempotent(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    pipeline = _pipeline(tmp_path / "out")
    result = pipeline.process(_bundle(_item(transcript), household_path=household))
    key = result["items"][0]["notification"]["idempotency_key"]

    first = pipeline.record_delivery(key, "wechat://receipt/1")
    second = pipeline.record_delivery(key, "wechat://receipt/1")
    replay = pipeline.process(_bundle(_item(transcript), household_path=household))

    assert first["status"] == "delivered"
    assert second["idempotent_replay"] is True
    assert replay["items"][0]["notification"]["status"] == "delivered"
    assert replay["items"][0]["notification"]["receipt"] == "wechat://receipt/1"
    with pytest.raises(DecisionError, match="blank"):
        pipeline.record_delivery(key, "  ")


def test_revised_advice_gets_new_notification_without_repeating_paper_trade(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    pipeline = _pipeline(tmp_path / "out")
    first_item = _item(transcript, ticker="QQQ")
    first = pipeline.process(_bundle(first_item, household_path=tmp_path / "unused.json"))

    revised_item = _item(transcript, ticker="QQQ")
    revised_item["notification_revision"] = "specific-signals-v2"
    revised_item["actionable_signals"][0]["execution"] = "修订后：只在放量止跌时执行。"
    revised = pipeline.process(
        _bundle(revised_item, household_path=tmp_path / "unused.json")
    )

    assert (
        first["items"][0]["notification"]["idempotency_key"]
        != revised["items"][0]["notification"]["idempotency_key"]
    )
    assert revised["items"][0]["idempotent_replay"] is False
    assert revised["items"][0]["book_kol_us"]["idempotent_replay"] is True
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 2
    assert len((tmp_path / "out" / "book_kol_us" / "decisions.jsonl").read_text().splitlines()) == 1


def test_corrected_attribution_gets_new_notification_without_repeating_paper_trade(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    pipeline = _pipeline(tmp_path / "out")
    original = _item(transcript, ticker="QQQ")
    first = pipeline.process(_bundle(original, household_path=tmp_path / "unused.json"))

    corrected = _item(transcript, author="吕晓彤", ticker="QQQ")
    corrected["title"] = "纠正后的文稿标题"
    second = pipeline.process(_bundle(corrected, household_path=tmp_path / "unused.json"))

    assert (
        first["items"][0]["notification"]["idempotency_key"]
        != second["items"][0]["notification"]["idempotency_key"]
    )
    assert second["items"][0]["idempotent_replay"] is False
    assert second["items"][0]["book_kol_us"]["idempotent_replay"] is True
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 2
    assert len((tmp_path / "out" / "book_kol_us" / "decisions.jsonl").read_text().splitlines()) == 1


def test_fresh_household_context_change_revises_notification_not_paper_trade(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    reads = []

    def loader():
        reads.append(len(reads) + 1)
        context = _household_context()
        context["positions"] = ([{
            "assetName": "科技ETF",
            "assetCode": "QQQ",
            "assetType": "fund",
            "currency": "USD",
            "currentAmount": 10,
            "costConfidence": "full",
        }] if reads[-1] == 1 else [])
        return context

    item = _item(transcript, ticker="QQQ")
    item["actionable_signals"][0]["relevant_asset_codes"] = ["QQQ"]
    pipeline = DecisionPipeline(tmp_path / "out", household_context_loader=loader)

    first = pipeline.process(_bundle(item, household_path=tmp_path / "unused.json"))
    second = pipeline.process(_bundle(item, household_path=tmp_path / "unused.json"))

    assert (
        first["items"][0]["notification"]["idempotency_key"]
        != second["items"][0]["notification"]["idempotency_key"]
    )
    assert second["items"][0]["idempotent_replay"] is False
    assert second["items"][0]["book_kol_us"]["idempotent_replay"] is True
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 2
    assert len((tmp_path / "out" / "book_kol_us" / "decisions.jsonl").read_text().splitlines()) == 1


def test_household_market_value_drift_does_not_resend_identical_reader_message(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    reads = []

    def loader():
        reads.append(len(reads) + 1)
        context = _household_context()
        context["positions"] = [{
            "assetName": "科技ETF",
            "assetCode": "QQQ",
            "assetType": "fund",
            "currency": "USD",
            "currentAmount": reads[-1] * 10,
            "costConfidence": "full",
        }]
        return context

    item = _item(transcript, ticker="QQQ")
    item["actionable_signals"][0]["relevant_asset_codes"] = ["QQQ"]
    pipeline = DecisionPipeline(tmp_path / "out", household_context_loader=loader)

    first = pipeline.process(_bundle(item, household_path=tmp_path / "unused.json"))
    second = pipeline.process(_bundle(item, household_path=tmp_path / "unused.json"))

    assert (
        first["items"][0]["notification"]["idempotency_key"]
        == second["items"][0]["notification"]["idempotency_key"]
    )
    assert second["items"][0]["idempotent_replay"] is True
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 1
    assert len((tmp_path / "out" / "book_kol_us" / "decisions.jsonl").read_text().splitlines()) == 1


def test_buy_rebalances_to_target_instead_of_adding_target_each_time(tmp_path):
    book = BookKolUs(tmp_path / "book")
    intent = _item(_write_text(tmp_path / "real.txt", "x"), ticker="QQQ")["book_kol_us"]

    first = book.route(intent, idempotency_key="evidence-1", evidence="real-1")
    second = book.route(intent, idempotency_key="evidence-2", evidence="real-2")

    assert first["notional"] == 35000.0
    assert second["status"] == "no_trade"
    assert second["concentration_risk"] == intent["concentration_risk"]
    assert second["exit_or_falsifier"] == intent["exit_or_falsifier"]
    assert book.account["cash"] == 65000.0


def test_each_replay_uses_fresh_household_context(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    reads = []

    def loader():
        reads.append(len(reads) + 1)
        context = _household_context()
        context["as_of"] = f"2026-07-19T18:0{reads[-1]}:00+08:00"
        context["decision_view"] = {
            "cashAvailable": reads[-1] * 100,
            "bucketExcesses": ["breakthrough"],
            "bucketShortfalls": ["foundation"],
        }
        context["positions"] = [{
            "assetName": "科技ETF",
            "assetCode": "QQQ",
            "assetType": "fund",
            "currency": "USD",
            "currentAmount": reads[-1] * 10,
            "costConfidence": "full",
        }]
        return context

    item = _item(transcript)
    item["household_recommendation"]["relevant_asset_codes"] = ["QQQ"]
    pipeline = DecisionPipeline(tmp_path / "out", household_context_loader=loader)

    first = pipeline.process(_bundle(item, household_path=household))
    second = pipeline.process(_bundle(item, household_path=household))

    assert len(reads) == 2
    assert first["items"][0]["household_context_assessment"]["cash_available_cny"] == 100
    assert second["items"][0]["household_context_assessment"]["cash_available_cny"] == 200


def test_sell_can_target_zero_for_full_liquidation(tmp_path):
    book = BookKolUs(tmp_path / "book")
    buy = _item(_write_text(tmp_path / "real.txt", "x"), ticker="QQQ")["book_kol_us"]
    book.route(buy, idempotency_key="buy", evidence="real")
    sell = {**buy, "side": "sell", "target_weight": 0}

    result = book.route(sell, idempotency_key="sell", evidence="real")

    assert result["status"] == "filled"
    assert book.account["positions"]["QQQ"]["quantity"] == 0
    assert book.account["cash"] == 100000.0


def test_batch_cash_feasibility_is_checked_before_any_side_effect(tmp_path):
    household = _write_household(tmp_path / "household.json")
    first_doc = _write_text(tmp_path / "one.txt", "等待成交量放大再行动")
    second_doc = _write_text(tmp_path / "two.txt", "第二份真实证据：等待成交量放大再行动")
    first = _item(first_doc, author="甲", ticker="QQQ")
    second = _item(second_doc, author="乙", ticker="SPY")
    first["book_kol_us"]["target_weight"] = 0.7
    second["book_kol_us"]["target_weight"] = 0.7
    bundle = {
        "household_context_provider": {"type": "lianghui_mcp"},
        "items": [first, second],
        "cross_source": {"agreements": [], "conflicts": []},
    }

    with pytest.raises(DecisionError, match="negative cash"):
        _pipeline(tmp_path / "out").process(bundle)

    assert not (tmp_path / "out" / "household_outbox.jsonl").exists()
    assert not (tmp_path / "out" / "book_kol_us" / "account.json").exists()


@pytest.mark.parametrize("field,value", [
    ("listing_country", "CN"),
    ("instrument_type", "future"),
    ("instrument_type", "option"),
    ("side", "short"),
    ("uses_margin", True),
])
def test_book_kol_us_fails_closed_but_allows_inverse_etf(tmp_path, field, value):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    household = _write_household(tmp_path / "household.json")
    item = _item(transcript, ticker="SQQQ")
    item["book_kol_us"][field] = value

    with pytest.raises(DecisionError):
        _pipeline(tmp_path / "out").process(_bundle(item, household_path=household))

    item = _item(transcript, ticker="SQQQ")
    item["book_kol_us"]["leveraged_or_inverse"] = True
    result = _pipeline(tmp_path / "allowed").process(
        _bundle(item, household_path=household)
    )
    assert result["items"][0]["book_kol_us"]["status"] == "filled"
