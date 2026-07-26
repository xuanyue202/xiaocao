from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from xiaocao.kol.longitudinal import (
    LUCIFER_UNCERTAIN,
    XIAOCAO_UNCERTAIN,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _thesis(
    thesis_id: str,
    *,
    subject: str,
    stance: str,
    impact: str = "high",
) -> dict[str, Any]:
    return {
        "thesis_id": thesis_id,
        "role": "primary_recommendation",
        "decision_relevance": "must_surface",
        "importance_basis": ["material_impact_thesis"],
        "claim_ids": [f"claim-{thesis_id}"],
        "subject": subject,
        "stance": stance,
        "horizon": "按来源条件持续评估",
        "attribution": "作者本人",
        "evidence_refs": [
            {
                "segment_id": f"segment-{thesis_id}",
                "quotes": [f"{subject}：{stance}"],
            }
        ],
        "priority": {
            "rank": 1,
            "urgency": "medium",
            "potential_impact": impact,
            "specificity": "medium",
            "user_relevance": "unknown",
            "reason": "脱敏夹具保留已受审观点顺序。",
        },
    }


def _gold(
    *,
    author: str,
    title: str,
    published_at: str,
    evidence_label: str,
    reader_message: str,
    theses: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence_sha256 = _sha(evidence_label)
    return {
        "item": {
            "author": author,
            "title": title,
            "published_at": published_at,
            "evidence_sha256": evidence_sha256,
            "reader_briefing": {
                "title": title,
                "paragraphs": [
                    {
                        "kind": "kol",
                        "thesis_ids": [
                            str(thesis["thesis_id"]) for thesis in theses
                        ],
                        "text": reader_message,
                    }
                ],
            },
            "investment_thesis_inventory": {
                "theses": theses,
            },
        },
        "validation": {"evidence_sha256": evidence_sha256},
        "reader_message": reader_message,
    }


def _write(root: Path, relative: str, value: dict[str, Any]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def materialize_reviewed_artifacts(root: Path) -> Path:
    """Create small, synthetic reviewed inputs without raw transcripts."""

    lucifer_current_ids = [
        "spacex-short-after-july-7",
        "beite-pullback-watch",
        "gold-near-term-rebound",
        "gold-tactical-trim",
        "physical-ai-energy-etf",
        "ai-bubble-winter-window",
        *[f"lucifer-current-{index:02d}" for index in range(1, 14)],
    ]
    lucifer_theses = []
    reader_subjects = {
        "gold-near-term-rebound": "黄金短期反弹",
        "gold-tactical-trim": "黄金战术减仓",
        "physical-ai-energy-etf": "物理人工智能与能源ETF",
        "ai-bubble-winter-window": "人工智能泡沫风险窗口",
    }
    for index, thesis_id in enumerate(
        lucifer_current_ids + sorted(LUCIFER_UNCERTAIN),
        start=1,
    ):
        if thesis_id == "spacex-short-after-july-7":
            subject = "SpaceX"
            stance = "7月7日后用总资金5%以下做空，绝不加杠杆"
        elif thesis_id == "beite-pullback-watch":
            subject = "北特科技"
            stance = "作者约40元买入，等待市场修复与个股企稳"
        else:
            subject = reader_subjects.get(
                thesis_id,
                f"路西法受审历史观点{index}",
            )
            stance = "保留来源观点及条件，行动前重新核实"
        lucifer_theses.append(
            _thesis(thesis_id, subject=subject, stance=stance)
        )
    assert len(lucifer_theses) == 32
    _write(
        root,
        (
            "output/live/kol_subscription_videos/review/"
            "lucifer_20260705_claim_gold_v4.json"
        ),
        _gold(
            author="路西法",
            title="投资情报｜路西法 7 月 5 日",
            published_at="2026-07-05T12:00:00+08:00",
            evidence_label="lucifer-reviewed-fixture",
            reader_message=(
                "路西法认为，SpaceX 在7月7日后可用总资金5%以下做空，"
                "绝不加杠杆。其余观点保留来源条件并等待按需核实。"
            ),
            theses=lucifer_theses,
        ),
    )

    xiaocao_specs = [
        (
            "broad-decline-low-level-rotation",
            "A股整体环境与风格",
            "整体仍弱，低位轮动而非全面进攻",
        ),
        (
            "rotation-range-rhythm",
            "轮动区间交易节奏",
            "按轮动区间控制节奏，避免追高",
        ),
        (
            "do-not-trade-if-uncomprehended",
            "认知边界",
            "看不懂的机会不交易",
        ),
        ("current-market-04", "短线情绪", "观察修复强度"),
        ("current-market-05", "仓位控制", "弱市控制风险预算"),
        ("current-market-06", "高低切换", "优先识别低位承接"),
        ("current-market-07", "指数结构", "指数强不等于普涨"),
        ("current-market-08", "次日验证", "等待量价确认"),
        (
            "eight-session-2021-analogy",
            "2021八日类比",
            "历史类比仍需后续盘面确认",
        ),
        (
            "changxin-not-sector-only-drain",
            "长鑫资金分流",
            "潜在分流尚未发生，保留待确认",
        ),
    ]
    assert {row[0] for row in xiaocao_specs} >= XIAOCAO_UNCERTAIN
    _write(
        root,
        (
            "output/live/kol_netdisk_enrichment/review/"
            "xiaocao_20260724_claim_gold_v1.json"
        ),
        _gold(
            author="小草",
            title="投资情报｜小草 7 月 24 日",
            published_at="2026-07-24T17:30:00+08:00",
            evidence_label="xiaocao-reviewed-fixture",
            reader_message=(
                "小草认为A股整体仍弱，应按轮动区间控制节奏，"
                "优先观察低位承接并避免追高。"
            ),
            theses=[
                _thesis(thesis_id, subject=subject, stance=stance)
                for thesis_id, subject, stance in xiaocao_specs
            ],
        ),
    )

    _write(
        root,
        (
            "output/live/kol_lv_subscription/review/"
            "lv_20260723_image_claim_gold_v1.json"
        ),
        _gold(
            author="吕晓彤",
            title="投资情报｜吕晓彤订阅图片",
            published_at="2026-07-23T12:00:00+08:00",
            evidence_label="lv-image-reviewed-fixture",
            reader_message=(
                "图片中的观点来自群聊参与者，不能归属于吕晓彤；"
                "因此只保留完整报告，不虚构长期观点。"
            ),
            theses=[],
        ),
    )

    lv_claims = []
    for claim_id, direction in (
        ("lv-20260720-remove-leverage", "卸掉杠杆产品"),
        ("lv-20260720-etf-versus-stock", "区分ETF与个股表达"),
        ("lv-20260720-apple-pullback", "等待苹果回调条件"),
    ):
        lv_claims.append(
            {
                "claim_id": claim_id,
                "asset_scope": [claim_id],
                "direction": direction,
                "horizon": "未来数月",
                "reasoning": "保留来源给出的风险和工具边界。",
                "falsifiers": ["条件变化时重新评估"],
                "quote": direction,
            }
        )
    lv_evidence_sha256 = _sha("lv-video-reviewed-fixture")
    _write(
        root,
        (
            "output/live/kol_subscription_videos/enrichment/"
            "051231a20050519b6514a8d566f2473e6135be3095f32abf8f22b3506ca51aac/"
            "artifacts/kol-netdisk-cloud-d5f607550bbd9dee/decision_result.json"
        ),
        {
            "items": [
                {
                    "author": "吕晓彤",
                    "published_at": "2026-07-20T12:00:00+08:00",
                    "evidence_sha256": lv_evidence_sha256,
                    "claims": lv_claims,
                    "market_outlook": {
                        "base_case": "科技方向保留，但必须卸掉杠杆。"
                    },
                    "system_synthesis": {
                        "summary": "保留非杠杆科技暴露，等待明确触发。"
                    },
                    "actionable_signals": [
                        {
                            "execution": "先卸掉杠杆产品",
                            "trigger": "风险暴露超出家庭预算",
                        }
                    ],
                    "book_kol_us": {
                        "status": "no_trade",
                        "reason": "历史初始化不重放纸面动作。",
                    },
                }
            ]
        },
    )
    return root
