"""One-time audited reader-copy correction for Lv Xiaotong publications.

Viewpoints are immutable in 灰常亮. Reader-copy fixes therefore append a
clean viewpoint, invalidate only the machine-oriented projection record, and
link the replacement explicitly. Source evidence and the original record stay
in history.
"""

from __future__ import annotations

import copy
from typing import Any

from .initial_import import LV_VIDEO_READER_COPY
from .publication import (
    PublicationError,
    build_append_only_publication_update,
    build_record,
    evaluation_id,
    relation_id,
    stable_claim,
    viewpoint_id,
)


CORRECTION_AS_OF = "2026-07-26T13:10:00.000Z"
CORRECTION_REVISION = "reader-copy-natural-chinese-v2"
LV_JULY_13_REPORT_ID = (
    "kr_op7cr6fxghxehyhdlbvv2iklupwm2c34hwjvezzxfaqgpqxdu2iq"
)
LV_JULY_20_REPORT_ID = (
    "kr_erermnq2preqzlw4hb4ased622if2grozn2ywvih5lnbr7nzo3ja"
)

LV_JULY_13_READER_COPY = {
    "legacy-market-posture": {
        "subject": "跨市场科技配置与去杠杆",
        "stance": (
            "科技方向要分层处理：降低存储芯片、通信和光模块暴露，"
            "停止使用杠杆产品，同时保留非杠杆人工智能与国产半导体"
            "设备方向；韩国杠杆资金出清和涨价预期拥挤仍可能带来"
            "二次下跌。"
        ),
    },
    "legacy-direction-070a5a543435e4ff": {
        "subject": "存储芯片",
        "stance": (
            "清仓或降低高拥挤的存储芯片仓位，等待韩国杠杆资金出清"
            "及盈利预期重新确认后再评估。"
        ),
    },
    "legacy-direction-973a3b0060140618": {
        "subject": "通信与光模块",
        "stance": (
            "已经降低通信与光模块仓位；在估值偏高、交易拥挤时，"
            "人工智能相关性不足以抵消回撤风险。"
        ),
    },
    "legacy-direction-161332dd5ba244f1": {
        "subject": "人工智能",
        "stance": (
            "长期保留人工智能方向，但只用非杠杆股票或ETF表达；"
            "具体标的、估值与入场条件仍需单独验证。"
        ),
    },
    "legacy-direction-0c4f91af8315e6c8": {
        "subject": "半导体设备",
        "stance": (
            "半导体设备的逻辑来自长鑫扩产和设备采购，不应与存储"
            "芯片涨价逻辑混为一谈；仍需跟踪资本开支兑现情况。"
        ),
    },
}

LV_JULY_13_ORDER = [
    "legacy-market-posture",
    "legacy-direction-070a5a543435e4ff",
    "legacy-direction-973a3b0060140618",
    "legacy-direction-161332dd5ba244f1",
    "legacy-direction-0c4f91af8315e6c8",
]
LV_JULY_20_ORDER = [
    "lv-20260720-remove-leverage",
    "lv-20260720-etf-versus-stock",
    "lv-20260720-apple-pullback",
]

LV_JULY_13_REPORT_COPY = {
    "title": "吕晓彤 7月13日会员直播：科技配置去杠杆与产业分化",
    "summary": (
        "吕晓彤明确主张降低存储芯片、通信和光模块仓位并停止使用"
        "杠杆产品，同时保留非杠杆人工智能和受扩产采购驱动的国产"
        "半导体设备方向；不同科技产业链不能用同一套涨价逻辑处理。"
    ),
    "report_body": """# 吕晓彤 7月13日会员直播：科技配置去杠杆与产业分化

## KOL关键观点

吕晓彤并非笼统看多科技。她明确主张降低存储芯片、通信和光模块仓位，停止使用倍数产品，同时保留人工智能、机器人以及受长鑫扩产驱动的半导体设备方向。

她的核心判断是：存储芯片涨价可能受到苹果等强势下游议价、韩国杠杆资金出清和新增供给压制；半导体设备赚的是长鑫扩产采购，不应与存储芯片涨价逻辑一起处理；长期人工智能方向可以保留，但应使用非杠杆股票或ETF表达。

## 分方向整理

- 存储芯片：清仓或降低高拥挤仓位，等待韩国杠杆资金出清及盈利预期重新确认后再评估。
- 通信与光模块：已经降低仓位；在估值偏高、交易拥挤时，人工智能相关性不足以抵消回撤风险。
- 人工智能：长期方向可以保留，但只用非杠杆股票或ETF表达，具体标的、估值与入场条件仍需单独验证。
- 半导体设备：逻辑来自长鑫扩产和设备采购，不应与存储芯片涨价逻辑混为一谈，仍需跟踪资本开支兑现情况。

## 系统补充与家庭边界

这组跨市场科技判断不直接替代A股短期市场判断，只作为产业分化和风险控制的补充。可复用的方法是把下游议价权、芯片价格和设备资本开支分开判断，并把长期方向与杠杆工具分开处理。

本次只是历史报告的读者文案纠错，不重新发送家庭提醒，也不重放任何 Book KOL-US 纸面动作。""",
}

LV_JULY_20_REPORT_COPY = {
    "title": "吕晓彤 7月20日直播：科技去杠杆与苹果观察条件",
    "summary": (
        "吕晓彤把科技急跌解释为拥挤交易和融资盘踩踏，明确反对"
        "长期持有两倍、三倍科技多头产品；非杠杆ETF与个股必须"
        "分开处理，苹果（AAPL）只有在价格、估值和基本面条件"
        "形成安全边际后才进入候选。"
    ),
    "report_body": """# 吕晓彤 7月20日直播：科技去杠杆与苹果观察条件

## KOL关键观点

吕晓彤把这次全球科技急跌解释为拥挤交易、融资盘和量化资金相互踩踏形成的快速去杠杆，而不是单一公司的普通回调。她明确反对长期持有两倍、三倍科技多头产品：长期看多科技并不能抵消高波动路径中的损耗和强平风险。

她认为非杠杆行业ETF与个股必须分开处理。ETF具有成分调整机制，但这不等于任何买入价都一定快速修复，因此既不要恐慌卖出，也不要仅凭“必然涨回”追加仓位。她还把苹果（AAPL）列为下跌后的候选机会，但没有给出价格、估值或确认条件，目前只能观察，不能直接执行。

## 系统核对与家庭边界

截至原分析时点，市场广度仍弱，科技内部表现分化，支持先去杠杆、再区分ETF与个股，不支持立即给科技方向加仓。家庭组合应先确认是否存在两倍、三倍科技多头产品；非杠杆ETF等待市场广度与相对强度重新确认；苹果（AAPL）需要补齐价格、估值、需求和利润率验证。

## Book KOL-US

原文点名的美股多为历史举例或缺少明确入场条件，因此纸面结果为暂不交易。

本次只是历史报告的读者文案纠错，不重新发送家庭提醒，也不重放任何 Book KOL-US 纸面动作。""",
}


def _report(current: dict[str, Any]) -> dict[str, Any]:
    report = current.get("report")
    if not isinstance(report, dict):
        raise PublicationError("reader-copy correction lacks current report")
    if report.get("record_id") not in {
        LV_JULY_13_REPORT_ID,
        LV_JULY_20_REPORT_ID,
    }:
        raise PublicationError("reader-copy correction got an unknown report")
    if report.get("payload", {}).get("kol_id") != "kol-lv-xiaotong":
        raise PublicationError("reader-copy correction is not bound to 吕晓彤")
    return report


def _viewpoints(current: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for record in current.get("records", []):
        if record.get("kind") != "viewpoint":
            continue
        local_id = str(record.get("payload", {}).get("local_thesis_id") or "")
        if local_id:
            rows[local_id] = record
    return rows


def _latest_evaluations(
    current: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for record in current.get("records", []):
        if record.get("kind") != "viewpoint_evaluation":
            continue
        viewpoint_id_value = str(
            record.get("payload", {}).get("viewpoint_id") or ""
        )
        previous = rows.get(viewpoint_id_value)
        if previous is None or (
            str(record["payload"].get("evaluated_at") or ""),
            str(record["record_id"]),
        ) > (
            str(previous["payload"].get("evaluated_at") or ""),
            str(previous["record_id"]),
        ):
            rows[viewpoint_id_value] = record
    return rows


def _replacement_viewpoint(
    old: dict[str, Any],
    reader_copy: dict[str, str],
) -> dict[str, Any]:
    payload = copy.deepcopy(old["payload"])
    old_local_id = str(payload["local_thesis_id"])
    local_id = old_local_id + "-reader-cn-v2"
    record_id_value = viewpoint_id(
        str(payload["report_id"]),
        local_id,
        payload["evidence_refs"],
    )
    payload.update(
        {
            "viewpoint_id": record_id_value,
            "local_thesis_id": local_id,
            "subject": reader_copy["subject"],
            "stance": reader_copy["stance"],
        }
    )
    publication_id = str(old["source_binding"]["publication_id"])
    return build_record(
        kind="viewpoint",
        record_id_value=record_id_value,
        idempotency_key=stable_claim(
            "put",
            publication_id,
            CORRECTION_REVISION,
            record_id_value,
        ),
        created_at=CORRECTION_AS_OF,
        source_binding=old["source_binding"],
        payload=payload,
    )


def _evaluation(
    viewpoint: dict[str, Any],
    *,
    status: str,
    basis: str,
    confidence: str,
    uncertainties: list[str],
    label: str,
) -> dict[str, Any]:
    viewpoint_id_value = str(viewpoint["record_id"])
    record_id_value = evaluation_id(
        viewpoint_id_value,
        CORRECTION_AS_OF,
        CORRECTION_AS_OF,
    )
    publication_id = str(viewpoint["source_binding"]["publication_id"])
    return build_record(
        kind="viewpoint_evaluation",
        record_id_value=record_id_value,
        idempotency_key=stable_claim(
            "put",
            publication_id,
            CORRECTION_REVISION,
            label,
            record_id_value,
        ),
        created_at=CORRECTION_AS_OF,
        source_binding=viewpoint["source_binding"],
        payload={
            "evaluation_id": record_id_value,
            "viewpoint_id": viewpoint_id_value,
            "status": status,
            "as_of": CORRECTION_AS_OF,
            "evaluated_at": CORRECTION_AS_OF,
            "basis": basis,
            "confidence": confidence,
            "uncertainties": uncertainties,
        },
    )


def _relation(
    *,
    source_binding: dict[str, Any],
    from_viewpoint_id: str,
    to_viewpoint_id: str,
    relation_type: str,
    reason: str,
    label: str,
) -> dict[str, Any]:
    record_id_value = relation_id(
        from_viewpoint_id,
        to_viewpoint_id,
        relation_type,
        CORRECTION_AS_OF,
    )
    publication_id = str(source_binding["publication_id"])
    return build_record(
        kind="viewpoint_relation",
        record_id_value=record_id_value,
        idempotency_key=stable_claim(
            "put",
            publication_id,
            CORRECTION_REVISION,
            label,
            record_id_value,
        ),
        created_at=CORRECTION_AS_OF,
        source_binding=source_binding,
        payload={
            "relation_id": record_id_value,
            "from_viewpoint_id": from_viewpoint_id,
            "to_viewpoint_id": to_viewpoint_id,
            "relation_type": relation_type,
            "asserted_at": CORRECTION_AS_OF,
            "reason": reason,
        },
    )


def build_lv_reader_copy_correction(
    current: dict[str, Any],
    *,
    prior_replacements: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build one exact append-only correction from a published manifest."""

    report = _report(current)
    report_id_value = str(report["record_id"])
    if report_id_value == LV_JULY_13_REPORT_ID:
        copy_by_local = LV_JULY_13_READER_COPY
        order = LV_JULY_13_ORDER
        report_copy = LV_JULY_13_REPORT_COPY
    else:
        copy_by_local = LV_VIDEO_READER_COPY
        order = LV_JULY_20_ORDER
        report_copy = LV_JULY_20_REPORT_COPY
    viewpoints = _viewpoints(current)
    latest_evaluations = _latest_evaluations(current)
    missing = [local_id for local_id in order if local_id not in viewpoints]
    if missing:
        raise PublicationError(
            "reader-copy correction is missing viewpoints: "
            + ", ".join(missing)
        )

    additions: list[dict[str, Any]] = []
    replacements: dict[str, str] = {}
    new_viewpoints: list[dict[str, Any]] = []
    for local_id in order:
        old = viewpoints[local_id]
        old_evaluation = latest_evaluations.get(str(old["record_id"]))
        if old_evaluation is None:
            raise PublicationError(
                f"reader-copy correction lacks evaluation for {local_id}"
            )
        replacement = _replacement_viewpoint(old, copy_by_local[local_id])
        replacements[local_id] = str(replacement["record_id"])
        new_viewpoints.append(replacement)
        additions.append(replacement)
        old_payload = old_evaluation["payload"]
        additions.append(
            _evaluation(
                replacement,
                status=str(old_payload["status"]),
                basis=(
                    "此次只纠正读者展示文案，不改变来源观点或原有当前性"
                    "判断。"
                    + str(old_payload["basis"])
                ),
                confidence=str(old_payload.get("confidence") or "medium"),
                uncertainties=[
                    str(value)
                    for value in old_payload.get("uncertainties", [])
                    if str(value).strip()
                ],
                label="replacement-currentness",
            )
        )
        additions.append(
            _evaluation(
                old,
                status="invalidated",
                basis=(
                    "该记录的来源观点没有被推翻；它仅因读者可见主题或"
                    "结论包含内部英文标签、不连贯表达或不清楚的行业"
                    "简称，被新的自然中文记录替代，因此不再进入当前区。"
                ),
                confidence="high",
                uncertainties=[],
                label="machine-copy-invalidated",
            )
        )
        additions.append(
            _relation(
                source_binding=old["source_binding"],
                from_viewpoint_id=str(replacement["record_id"]),
                to_viewpoint_id=str(old["record_id"]),
                relation_type="replaces",
                reason=(
                    "新记录只纠正读者展示语言并保留原来源证据；旧记录"
                    "永久留在历史时间线，不发生静默覆盖。"
                ),
                label="reader-copy-replaces",
            )
        )

    if report_id_value == LV_JULY_20_REPORT_ID:
        prior = prior_replacements or {}
        required = {
            "legacy-market-posture",
            "legacy-direction-161332dd5ba244f1",
        }
        if not required <= set(prior):
            raise PublicationError(
                "July 20 correction lacks corrected July 13 dependencies"
            )
        additions.extend(
            [
                _relation(
                    source_binding=report["source_binding"],
                    from_viewpoint_id=replacements[
                        "lv-20260720-remove-leverage"
                    ],
                    to_viewpoint_id=prior["legacy-market-posture"],
                    relation_type="refines",
                    reason=(
                        "7月20日把7月13日的科技去杠杆原则进一步细化为"
                        "停止新增倍数产品，并优先降低已有杠杆暴露。"
                    ),
                    label="corrected-cross-report-refines",
                ),
                _relation(
                    source_binding=report["source_binding"],
                    from_viewpoint_id=replacements[
                        "lv-20260720-etf-versus-stock"
                    ],
                    to_viewpoint_id=prior[
                        "legacy-direction-161332dd5ba244f1"
                    ],
                    relation_type="refines",
                    reason=(
                        "7月20日进一步说明，长期科技和人工智能暴露可以"
                        "保留，但非杠杆ETF与个股需要分别验证。"
                    ),
                    label="corrected-cross-report-refines",
                ),
            ]
        )

    current_viewpoint_ids = list(
        report["payload"].get("viewpoint_ids") or []
    )
    viewpoint_ids = [
        *[str(row["record_id"]) for row in new_viewpoints],
        *current_viewpoint_ids,
    ]
    records, publish = build_append_only_publication_update(
        current_records=current["records"],
        additions=additions,
        viewpoint_ids=viewpoint_ids,
        created_at=CORRECTION_AS_OF,
        revision=CORRECTION_REVISION,
        reason=(
            "纠正读者可见标题与观点文案；保留来源证据和历史记录，"
            "不创建提醒、不重放Book"
        ),
        report_payload_updates=report_copy,
    )
    return {
        "publication_key": f"{CORRECTION_REVISION}:{report_id_value}",
        "records": records,
        "publish_request": publish,
        "metadata": {
            "historical": True,
            "reader_copy_correction": True,
            "notification_claim_authorized": False,
            "book_kol_us_replay_authorized": False,
            "notification_claims_created": 0,
            "book_kol_us_replays": 0,
            "large_payload_local_bytes": 0,
            "replacements": replacements,
        },
    }
