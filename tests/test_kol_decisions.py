from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from xiaocao.kol.decisions import (
    BookKolUs,
    DecisionError,
    DecisionPipeline,
    TranscriptDocument,
    render_household_item_message,
)
from xiaocao.kol.rendering import reader_message_title


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


def _market_outlook(**overrides) -> dict:
    outlook = {
        "scope": "A股整体",
        "claim_ids": ["小草-risk"],
        "current_phase": "风险释放尚未完成。",
        "base_case": "低位放量前继续防守。",
        "strategy": ["控制高贝塔仓位"],
        "turning_points": ["低位显著放量"],
        "horizon": "未来一至两周",
        "confidence": "high",
        "falsifiers": ["放量后继续破位"],
        "current_validation": {
            "status": "qualify",
            "as_of": "2026-07-19T18:00:00+08:00",
            "summary": "周末无新增交易日，等待下一交易日确认。",
            "currentness": {
                "latest_available": True,
                "checked_at": "2026-07-19T18:00:00+08:00",
                "reason": "周末无新增交易日。",
            },
            "facts": [{
                "metric": "market_session",
                "value": "closed",
                "observed_at": "2026-07-19T16:00:00+08:00",
                "evidence": "frozen://market/2026-07-19",
                "reader_text": "7月19日周末休市，最新可用交易日不变。",
            }],
        },
    }
    outlook.update(overrides)
    return outlook


def test_transcript_document_reads_plain_text_and_requires_exact_quote(tmp_path):
    path = _write_text(tmp_path / "real.txt", "今天的结论：等待成交量放大再行动。")
    document = TranscriptDocument.load(path)

    assert document.contains("等待成交量放大再行动")
    assert len(document.sha256) == 64
    assert document.text_length > 10


def test_committed_acceptance_does_not_persist_household_account_state():
    acceptance = (
        Path(__file__).parents[1]
        / "reference/experience/acceptance/kol_decisions_2026-07-19.json"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "家庭真实持有",
        "家庭真实组合仍持有",
        "家庭账户仍持有",
        "真实组合卖出",
    ):
        assert forbidden not in acceptance


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


def test_no_reader_insight_is_audited_but_never_sent(tmp_path):
    transcript = _write_text(tmp_path / "empty-insight.txt", "等待成交量放大再行动")
    item = _item(transcript)
    item.update(
        {
            "decision_status": "no_actionable_signal",
            "decision_reason": "原文不足以形成交易判断。",
            "reader_insight": {
                "status": "none",
                "reason": "没有可准确复述给读者的新洞察。",
            },
        }
    )
    checked_at = datetime.now(timezone.utc).isoformat()
    for validation in (
        item["market_validation"],
        item["actionable_signals"][0]["current_validation"],
    ):
        validation["as_of"] = checked_at
        validation["currentness"]["checked_at"] = checked_at
        validation["facts"][0]["observed_at"] = checked_at
    pipeline = _pipeline(tmp_path / "out")
    first = pipeline.process(_bundle(item, household_path=tmp_path / "unused.json"))
    second = pipeline.process(_bundle(item, household_path=tmp_path / "unused.json"))
    sends = 0

    def sender(_title, _body):
        nonlocal sends
        sends += 1
        return {"wecom": "ok"}

    delivery = pipeline.deliver_wechat(first, sender=sender)

    assert first["items"][0]["notification"]["status"] == "suppressed"
    assert first["items"][0]["notification"]["reason"] == (
        "没有可准确复述给读者的新洞察。"
    )
    assert second["items"][0]["idempotent_replay"] is True
    assert delivery["status"] == "already_delivered"
    assert sends == 0
    rows = (tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["status"] == "suppressed"


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


def test_cross_source_relation_requires_claims_from_distinct_authors(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript, author="吕晓彤")
    item["claims"].append({
        **item["claims"][0],
        "claim_id": "吕晓彤-second-risk",
    })
    bundle = _bundle(item, household_path=tmp_path / "unused.json")
    bundle["cross_source"]["conflicts"] = [{
        "topic": "same-author-is-not-cross-source",
        "claim_ids": ["吕晓彤-risk", "吕晓彤-second-risk"],
        "judgment": "同一作者的两个观点不能冒充跨来源冲突。",
    }]

    with pytest.raises(DecisionError, match="distinct authors"):
        _pipeline(tmp_path / "out").process(bundle)


def test_reader_message_surfaces_relevant_cross_author_judgment(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript, author="小草")
    cross_source = {
        "agreements": [{
            "topic": "risk",
            "claim_ids": ["小草-risk", "吕晓彤-risk"],
            "authors": ["小草", "吕晓彤"],
            "judgment": "两位都主张先降低高贝塔风险。",
        }],
        "conflicts": [],
    }

    message = render_household_item_message(item, cross_source)

    assert "多方共同信号" in message
    assert "小草、吕晓彤" in message
    assert "两位都主张先降低高贝塔风险" in message


def test_reader_message_surfaces_market_outlook_before_individual_signals(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript, author="小草")
    item["market_outlook"] = _market_outlook(
        current_phase="风险释放尚未完成，反弹仍按弱势修复看待。",
        base_case="低位显著放量前，大盘更可能反复磨底而不是直接反转。",
        strategy=["控制高贝塔仓位", "保留现金等待止跌确认"],
        turning_points=["低位显著放量", "市场广度停止恶化"],
    )

    message = render_household_item_message(item)

    assert "【大盘与整体策略：A股整体】" in message
    assert "作者原话：「等待成交量放大再行动」" in message
    assert "最新市场验证（截至 2026-07-19 18:00，有条件支持）" in message
    assert "关键事实：7月19日周末休市，最新可用交易日不变。（观察于 2026-07-19 16:00）" in message
    assert "今天盘面判断：风险释放尚未完成" in message
    assert "下一交易日计划：控制高贝塔仓位" in message
    assert "后续几天基础情景：低位显著放量前" in message
    assert "下一交易日计划：控制高贝塔仓位；保留现金等待止跌确认" in message
    assert "系统关注的关键转折：低位显著放量；市场广度停止恶化" in message
    assert "判断周期：未来一至两周（信心：高）" in message
    assert message.index("【大盘与整体策略：A股整体】") < message.index(
        "【暂不参与：A股短线】"
    )


def test_context_corrected_kol_message_separates_viewpoints_from_system_analysis(
    tmp_path,
):
    transcript = _write_text(
        tmp_path / "real.txt",
        "今天外面又是一片惨跌。低位是轮动的。听不懂就不做。",
    )
    item = _item(transcript, author="小草")
    item["claims"] = [
        {
            **item["claims"][0],
            "claim_id": "market",
            "quote": "今天外面又是一片惨跌。",
            "reader_quote": "当天是普跌环境，但轻仓账户本身没有大问题。",
        },
        {
            **item["claims"][0],
            "claim_id": "rotation",
            "quote": "低位是轮动的。",
            "reader_quote": "当前位置是低位轮动，没有明确主线。",
        },
    ]
    item["synthesis"].update(
        {
            "reader_render_mode": "kol_context_corrected",
            "reader_quote_ids": ["market", "rotation"],
            "analysis_points": [
                "这不是看多市场，而是在弱市里比较相对强弱。",
                "执行重点是控制总仓位，不因单票上涨放大风险。",
            ],
            "system_check": "收盘上涨555家、下跌4939家。",
            "system_advice": "等待，不新增仓位。",
        }
    )

    message = render_household_item_message(item)

    assert reader_message_title(item) == "投资情报｜小草：直播观点拆解"
    assert message.startswith("【KOL观点｜小草｜按逐字稿上下文校正】")
    assert "- 当天是普跌环境，但轻仓账户本身没有大问题。" in message
    assert "- 当前位置是低位轮动，没有明确主线。" in message
    assert "今天外面又是一片惨跌" not in message
    assert "【系统拆解｜对KOL逻辑的分析】" in message
    assert "- 这不是看多市场，而是在弱市里比较相对强弱。" in message
    assert "【系统核对｜仅补事实】\n收盘上涨555家、下跌4939家。" in message
    assert "【系统结论】\n等待，不新增仓位。" in message
    assert "今天盘面判断" not in message
    assert "系统关注的关键转折" not in message
    assert "发生了什么" not in message

    payload_kwargs = {
        "author": item["author"],
        "title": item["title"],
        "claims": item["claims"],
        "actionable_signals": [],
        "market_outlook": {},
        "synthesis": item["synthesis"],
        "household_recommendation": {},
        "cross_source": {"agreements": [], "conflicts": []},
    }
    original_payload = DecisionPipeline._notification_payload(
        **payload_kwargs
    )
    item["claims"][0]["reader_quote"] = "当天市场普跌，账户依靠轻仓规避冲击。"
    revised_payload = DecisionPipeline._notification_payload(
        **payload_kwargs
    )
    assert original_payload != revised_payload


def test_no_actionable_reader_message_is_short_and_only_links_real_holding(tmp_path):
    transcript = _write_text(tmp_path / "17.png.txt", "特斯拉才叫崩啊")
    item = _item(transcript, author="吕晓彤", ticker="TSLA")
    item.update(
        {
            "decision_status": "no_actionable_signal",
            "decision_reason": "群聊片段无法确认作者归属。",
            "reader_insight": {
                "status": "useful",
                "summary": "群内有人明确提到特斯拉下跌，反映当时短线风险情绪偏弱。",
                "boundary": "这不是吕晓彤本人确认观点，也没有完整买卖条件。",
            },
            "source": "baidu_subscription_share_browser",
            "published_at": "2026-07-23T23:41:07+08:00",
            "title": "17.png",
            "market_outlook": _market_outlook(scope="A股整体与美股大型科技观察"),
        }
    )
    item["actionable_signals"][0]["context_assessment"] = {
        "held": True,
        "relevant_positions": [
            {
                "asset_code": "TSLA",
                "asset_name": "特斯拉",
                "currency": "USD",
                "current_amount": 4695,
            }
        ],
    }

    message = render_household_item_message(item)

    assert reader_message_title(item) == "投资情报｜吕晓彤：弱信号提醒"
    assert message.splitlines() == [
        "【注意｜弱信号】",
        "洞察：群内有人明确提到特斯拉下跌，反映当时短线风险情绪偏弱。",
        "与你有关：家庭当前持有特斯拉（TSLA）；请注意波动，是否调整由你决定。",
        "边界：这不是吕晓彤本人确认观点，也没有完整买卖条件。",
        "来源：吕晓彤订阅｜2026-07-23 23:41｜百度网盘订阅图片｜17.png",
    ]
    assert "INTC" not in message
    assert "GOOGL" not in message
    assert "下一交易日" not in message
    assert "大盘与整体策略" not in message


def test_no_actionable_reader_message_does_not_force_household_analysis(tmp_path):
    transcript = _write_text(tmp_path / "18.png.txt", "大A现在是不是不跟美韩了")
    item = _item(transcript, author="吕晓彤")
    item.update(
        {
            "decision_status": "no_actionable_signal",
            "decision_reason": "只有无法归属的提问。",
            "reader_insight": {
                "status": "useful",
                "summary": "群内在讨论A股与海外市场的联动是否减弱。",
                "boundary": "原文只有提问，没有明确结论。",
            },
            "source": "baidu_subscription_share_browser",
            "published_at": "2026-07-24T09:00:00+08:00",
            "title": "18.png",
            "market_outlook": _market_outlook(claim_ids=["吕晓彤-risk"]),
        }
    )
    item["actionable_signals"][0]["context_assessment"] = {
        "held": False,
        "relevant_positions": [],
    }

    message = render_household_item_message(item)

    assert "洞察：群内在讨论A股与海外市场的联动是否减弱。" in message
    assert "家庭" not in message
    assert "今天盘面判断" not in message
    assert len(message.splitlines()) == 4


def test_reader_message_prioritizes_market_scope_and_normalizes_asr_entities(
    tmp_path,
):
    transcript = _write_text(
        tmp_path / "20260721 大师班专场(晚17：30开播)-compressed.txt",
        "科创芯片ETF就这个五八八七五零。",
    )
    item = _item(transcript, author="小草")
    item.update(
        {
            "source": "baidu_netdisk_opencli_dom",
            "published_at": "2026-07-21T17:30:00+08:00",
            "claims": [
                {
                    **item["claims"][0],
                    "quote": "科创芯片ETF就这个五八八七五零。",
                    "reader_quote": "科创芯片ETF（588750）只等回调，不追涨。",
                }
            ],
            "market_outlook": _market_outlook(
                claim_ids=["小草-risk"],
                scope="A股整体、趋势大票与半导体轮动",
                strategy=[
                    "588750.XSHG不追涨",
                    "趋势仓先用两到三成，短线情绪股继续等待",
                ],
            ),
        }
    )
    item["market_outlook"]["current_validation"]["facts"].append(
        {
            "metric": "semiconductor_leaders_close",
            "value": "688347.XSHG=92.30",
            "observed_at": "2026-07-19T16:00:00+08:00",
            "evidence": "frozen://market/2026-07-19",
        }
    )

    title = reader_message_title(item)
    message = render_household_item_message(item)
    notification_payload = DecisionPipeline._notification_payload(
        author=item["author"],
        title=item["title"],
        claims=item["claims"],
        actionable_signals=item["actionable_signals"],
        market_outlook=item["market_outlook"],
        synthesis=item["synthesis"],
        household_recommendation=item["household_recommendation"],
        cross_source={"agreements": [], "conflicts": []},
    )

    assert title == "投资情报｜小草：A股整体、趋势大票与半导体轮动"
    assert message.startswith("【大盘与整体策略：A股整体、趋势大票与半导体轮动】")
    assert "来源要点（转录已校正）：「科创芯片ETF（588750）只等回调，不追涨。」" in message
    assert "五八八七五零" not in message
    assert "588750.XSHG" not in message
    assert "semiconductor_leaders_close" not in message
    assert "688347.XSHG" not in message
    assert notification_payload["market_outlook"]["author_quotes"] == [
        "科创芯片ETF（588750）只等回调，不追涨。"
    ]
    assert (
        "信息来源：小草｜2026-07-21 17:30｜百度网盘原视频（完整文稿）｜"
        "大师班专场(晚17：30开播)"
    ) in message


def test_reader_message_labels_ticket05_video_sources(tmp_path):
    transcript = _write_text(tmp_path / "7月20日.txt", "等待成交量放大再行动")
    item = _item(transcript, author="吕晓彤")
    item.update(
        {
            "source": "baidu_subscription_share_browser",
            "media_type": "video",
            "published_at": "2026-07-20T00:00:00+08:00",
            "title": "吕晓彤7月20日",
            "market_outlook": _market_outlook(claim_ids=["吕晓彤-risk"]),
        }
    )

    lv_message = render_household_item_message(item)
    item.update(
        {
            "source": "baidu_private_folder",
            "author": "路西法",
            "title": "路西法7月5日（二）",
        }
    )
    lucifer_message = render_household_item_message(item)

    assert "百度网盘订阅视频（完整文稿）" in lv_message
    assert "百度网盘订阅图片" not in lv_message
    assert "百度网盘私有目录视频（完整文稿）" in lucifer_message


def test_material_market_outlook_change_creates_new_reader_notification(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    pipeline = _pipeline(tmp_path / "out")
    first_item = _item(transcript, author="小草")
    first_item["notification_revision"] = "market-outlook-v1"
    first_item["market_outlook"] = _market_outlook()

    first = pipeline.process(
        _bundle(first_item, household_path=tmp_path / "unused.json")
    )
    revised_item = _item(transcript, author="小草")
    revised_item["notification_revision"] = "market-outlook-v1"
    revised_item["market_outlook"] = {
        **first_item["market_outlook"],
        "current_phase": "低位放量已经出现，进入止跌确认阶段。",
        "base_case": "若市场广度同步修复，可从防守转向试仓。",
    }
    second = pipeline.process(
        _bundle(revised_item, household_path=tmp_path / "unused.json")
    )
    replay = pipeline.process(
        _bundle(revised_item, household_path=tmp_path / "unused.json")
    )

    assert first["items"][0]["notification"]["idempotency_key"] != second[
        "items"
    ][0]["notification"]["idempotency_key"]
    assert second["items"][0]["idempotent_replay"] is False
    assert replay["items"][0]["idempotent_replay"] is True
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 2


def test_market_outlook_must_link_back_to_this_items_claims(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript, author="小草")
    item["market_outlook"] = _market_outlook(claim_ids=["another-author-risk"])

    with pytest.raises(DecisionError, match="market outlook claim_ids"):
        _pipeline(tmp_path / "out").process(
            _bundle(item, household_path=tmp_path / "unused.json")
        )


def test_market_outlook_provenance_only_change_does_not_duplicate_notification(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    pipeline = _pipeline(tmp_path / "out")
    first_item = _item(transcript, author="小草")
    first_item["claims"].append({
        **first_item["claims"][0],
        "claim_id": "小草-alt-risk",
    })
    first_item["notification_revision"] = "market-outlook-v1"
    first_item["market_outlook"] = _market_outlook()

    first = pipeline.process(
        _bundle(first_item, household_path=tmp_path / "unused.json")
    )
    revised_item = _item(transcript, author="小草")
    revised_item["claims"].append({
        **revised_item["claims"][0],
        "claim_id": "小草-alt-risk",
    })
    revised_item["notification_revision"] = "market-outlook-v1"
    revised_item["market_outlook"] = {
        **first_item["market_outlook"],
        "claim_ids": ["小草-alt-risk"],
    }
    replay = pipeline.process(
        _bundle(revised_item, household_path=tmp_path / "unused.json")
    )

    assert replay["items"][0]["idempotent_replay"] is True
    assert replay["items"][0]["notification"]["idempotency_key"] == first[
        "items"
    ][0]["notification"]["idempotency_key"]
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 1


def test_reader_visible_market_fact_change_creates_new_notification(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    pipeline = _pipeline(tmp_path / "out")
    first_item = _item(transcript, author="小草")
    first_item["notification_revision"] = "market-outlook-v1"
    first_item["market_outlook"] = _market_outlook()
    first = pipeline.process(
        _bundle(first_item, household_path=tmp_path / "unused.json")
    )

    revised_item = _item(transcript, author="小草")
    revised_item["notification_revision"] = "market-outlook-v1"
    revised_item["market_outlook"] = _market_outlook()
    revised_item["market_outlook"]["current_validation"]["facts"][0].update({
        "value": "open",
        "observed_at": "2026-07-19T18:00:00+08:00",
        "reader_text": "市场已经恢复交易并出现低位放量。",
    })
    second = pipeline.process(
        _bundle(revised_item, household_path=tmp_path / "unused.json")
    )

    assert second["items"][0]["idempotent_replay"] is False
    assert second["items"][0]["notification"]["idempotency_key"] != first[
        "items"
    ][0]["notification"]["idempotency_key"]
    assert len((tmp_path / "out" / "household_outbox.jsonl").read_text().splitlines()) == 2


def test_market_outlook_requires_its_own_current_validation(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript, author="小草")
    item["market_outlook"] = _market_outlook()
    del item["market_outlook"]["current_validation"]

    with pytest.raises(DecisionError, match="market_outlook.current_validation"):
        _pipeline(tmp_path / "out").process(
            _bundle(item, household_path=tmp_path / "unused.json")
        )


def test_market_outlook_rejects_blank_reader_facing_list_values(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    item = _item(transcript, author="小草")
    item["market_outlook"] = _market_outlook(strategy=["   "])

    with pytest.raises(DecisionError, match="market outlook strategy values"):
        _pipeline(tmp_path / "out").process(
            _bundle(item, household_path=tmp_path / "unused.json")
        )


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


def test_material_paper_redecision_is_allowed_for_same_evidence(tmp_path):
    transcript = _write_text(tmp_path / "real.txt", "等待成交量放大再行动")
    pipeline = _pipeline(tmp_path / "out")
    first_item = _item(transcript)
    first = pipeline.process(_bundle(first_item, household_path=tmp_path / "unused.json"))

    revised_item = _item(transcript, ticker="QQQ")
    revised_item["market_validation"]["status"] = "support"
    revised_item["market_validation"]["summary"] = "新市场事实支持建立非杠杆科技仓位。"
    second = pipeline.process(
        _bundle(revised_item, household_path=tmp_path / "unused.json")
    )
    replay = pipeline.process(
        _bundle(revised_item, household_path=tmp_path / "unused.json")
    )

    assert first["items"][0]["book_kol_us"]["status"] == "no_trade"
    assert second["items"][0]["book_kol_us"]["status"] == "filled"
    assert second["items"][0]["book_kol_us"]["idempotent_replay"] is False
    assert replay["items"][0]["book_kol_us"]["idempotent_replay"] is True
    assert (
        first["items"][0]["book_kol_us"]["idempotency_key"]
        != second["items"][0]["book_kol_us"]["idempotency_key"]
    )
    decisions = tmp_path / "out" / "book_kol_us" / "decisions.jsonl"
    trades = tmp_path / "out" / "book_kol_us" / "trades.jsonl"
    assert len(decisions.read_text().splitlines()) == 2
    assert sum(
        json.loads(line).get("event") == "trade_filled"
        for line in trades.read_text().splitlines()
    ) == 1


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
