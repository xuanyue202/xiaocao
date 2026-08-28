# 小草每周深度复盘 2026-08-28

## 先看结论
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：4 个；另有 1 条本地工作区提醒，见下一节。

## 需要你看/确认的事项
- **需要确认** `quant-manager-capacity-panel-contract-2026-08-28`：定义量化管理人容量衰减面板合同
- **需要确认** `east-buy-fundamentals-panel-contract-2026-08-28`：定义东方甄选财季基本面板合同
- **需要确认** `usd-rate-transmission-research-contract-2026-08-28`：定义美元利率公司传导研究合同
- **需要确认** `volatile-asset-boundary-research-contract-2026-08-28`：定义波动资产边界纪律研究合同
- **本地工作区提醒，不是策略判断**：有 1 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl。

## 这批转录给我的启发
- **2026-08-22 review（2026-08-22_lv_xiaotong_review.json）**
  启发：把量化产品评估拆成选股、择时、风险预算、产品适配、容量衰减和跨市场可迁移性；所有胜率、年化和回撤口述都需滚动样本外与成本证据，三倍杠杆示例不进入家庭建议。
  姿态：not_applied_other_author：吕晓彤是其他作者，本条不修改posture_current或REGIME_TIMELINE。
  打法：no_deterministic_change：仅新增authority=0量化产品评估候选。
  待验证：one_new_candidate：管理人规模与容量衰减，等待滚动样本外检验。
  命中审计：bound_to_complete_transcript_sha256_f13ea0adb23ade8f5a12bf474359d6403433f88b09aa35cbc894fb5e9f7f2f7f
  工具缺口：建立管理人AUM、容量、换手、成本与后续3/6/12个月扣费超额面板。
- **2026-08-25 公司年报分析（2026-08-25_lv_xiaotong_review.json）**
  启发：吕晓彤用东方甄选2026财年上下半年的分部数据，判断管理层更替后的增长、订单和GMV改善，并把多账号矩阵、自营品、高价高毛利结构和线下即时零售视为后续驱动；同时指出自有App会员增长没有同步转化为收入，未来能力仍需验证。可复用的方法是把收入、GMV、订单、客单价、产品结构、平台流量和新业务投入拆开核验，而不是用单一年度增速外推长期回报。
  姿态：不应用：吕晓彤是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  打法：候选补充上下半年驱动拆解、平台大盘与公司份额区分、会员单位经济和新业务期权式核验。
  待验证：新增四条关于管理层策略识别、自营品护城河、会员商业化和线下即时零售单位经济的可证伪候选。
  命中审计：完整PDF证据共111个稳定分段，已覆盖财务、GMV、订单、产品、自有App、成本、线下零售和竞争判断；重复免责声明与页眉不进入投资论点。
  工具缺口：补充公司公告/年报与后续财季的自营品占比、复购、App订单和线下单点经济数据；不改动确定性策略。
- **2026-08-27 微信公众号复盘（2026-08-27_liu_shao_review.json）**
  启发：刘少狙击营认为9月利率大概率暂不变化，后续降息预期仍可能重新影响全球资产；其对A股高端制造的解释强调海外收入、美元结算和融资成本，但公司层面的利润传导尚未逐项核验。文章同时强调NVIDIA季度盈利与AI需求强劲，并记录机器人浮亏和比特币止盈边界。最可复用的知识是：宏观利率叙事要落到成本、利润和估值的连续验证；横盘期的波动资产应遵守预设止盈和波动边界。
  姿态：不应用：刘少狙击营是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  打法：no_change：利率传导和横盘止盈原则仅作为候选方法，未通过研究和人审门禁。
  待验证：two_new_candidates：新增海外收入制造的美元成本传导检验，以及横盘期预设边界相对热点反向操作的纪律检验。
  命中审计：完整微信公众号正文已按SHA-256 50793654465505876ec4b3c5564c20efae90cea4261216cd6a1a0645b4db5ee0归档；PCE、FOMC日期、NVIDIA季度数据和家庭风险预算另有本轮独立核验边界。
  工具缺口：research_candidate_only：后续建立美元利率—公司中间变量面板和波动资产边界纪律样本；未通过scripts/research_run.py与§10前不进入确定性策略。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-08-22 2026-08-22_lv_xiaotong_review.json: not_applied_other_author：吕晓彤是其他作者，本条不修改posture_current或REGIME_TIMELINE。
  - 2026-08-25 2026-08-25_lv_xiaotong_review.json: 不应用：吕晓彤是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  - 2026-08-27 2026-08-27_liu_shao_review.json: 不应用：刘少狙击营是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
- **Playbook/纪律**
  - 2026-08-22 2026-08-22_lv_xiaotong_review.json: no_deterministic_change：仅新增authority=0量化产品评估候选。
  - 2026-08-25 2026-08-25_lv_xiaotong_review.json: 候选补充上下半年驱动拆解、平台大盘与公司份额区分、会员单位经济和新业务期权式核验。
  - 2026-08-27 2026-08-27_liu_shao_review.json: no_change：利率传导和横盘止盈原则仅作为候选方法，未通过研究和人审门禁。
- **候选假设**
  - 2026-08-22 2026-08-22_lv_xiaotong_review.json: one_new_candidate：管理人规模与容量衰减，等待滚动样本外检验。
  - 2026-08-25 2026-08-25_lv_xiaotong_review.json: 新增四条关于管理层策略识别、自营品护城河、会员商业化和线下即时零售单位经济的可证伪候选。
  - 2026-08-27 2026-08-27_liu_shao_review.json: two_new_candidates：新增海外收入制造的美元成本传导检验，以及横盘期预设边界相对热点反向操作的纪律检验。
- **命中审计**
  - 2026-08-22 2026-08-22_lv_xiaotong_review.json: bound_to_complete_transcript_sha256_f13ea0adb23ade8f5a12bf474359d6403433f88b09aa35cbc894fb5e9f7f2f7f
  - 2026-08-25 2026-08-25_lv_xiaotong_review.json: 完整PDF证据共111个稳定分段，已覆盖财务、GMV、订单、产品、自有App、成本、线下零售和竞争判断；重复免责声明与页眉不进入投资论点。
  - 2026-08-27 2026-08-27_liu_shao_review.json: 完整微信公众号正文已按SHA-256 50793654465505876ec4b3c5564c20efae90cea4261216cd6a1a0645b4db5ee0归档；PCE、FOMC日期、NVIDIA季度数据和家庭风险预算另有本轮独立核验边界。
- **工具/流程提案**
  - 2026-08-22 2026-08-22_lv_xiaotong_review.json: 建立管理人AUM、容量、换手、成本与后续3/6/12个月扣费超额面板。
  - 2026-08-25 2026-08-25_lv_xiaotong_review.json: 补充公司公告/年报与后续财季的自营品占比、复购、App订单和线下单点经济数据；不改动确定性策略。
  - 2026-08-27 2026-08-27_liu_shao_review.json: research_candidate_only：后续建立美元利率—公司中间变量面板和波动资产边界纪律样本；未通过scripts/research_run.py与§10前不进入确定性策略。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：4
- 自动落地候选数量：0

## 验证
- bash scripts/auto_daily.sh weekly: PASS (terminal weekly plan ready; run exactly once)
- weekly routed plan structure: PASS (4 proposals; 0 auto-apply candidates)
- PYTHONPATH=src .venv/bin/python scripts/data_doctor.py: PASS (no dirty-data findings)
- PYTHONPATH=src .venv/bin/python scripts/status.py --json: PASS (A/B/T authoritative readback)
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src .venv/bin/python scripts/strategy_protocols.py --check: PASS (3 protocols)
- PYTHONPATH=src .venv/bin/python -m pytest tests/test_weekly_deep_review.py -q: PASS (14 passed)
- git diff --check: PASS

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 100 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-08-28/quant-manager-capacity-panel-contract-2026-08-28.md
- .scratch/weekly-deep-review/2026-08-28/east-buy-fundamentals-panel-contract-2026-08-28.md
- .scratch/weekly-deep-review/2026-08-28/usd-rate-transmission-research-contract-2026-08-28.md
- .scratch/weekly-deep-review/2026-08-28/volatile-asset-boundary-research-contract-2026-08-28.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 70,
    "candidate_assertions": 162,
    "candidate_to_tested": 0.1,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 100,
    "candidates_untested": 90,
    "dedup_ratio": 0.62,
    "instrumentation_todos": 39,
    "median_recurrence": 1.0,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 596,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 70
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 32,
  "pre_existing_dirty_sample": [
    " M kronos_screen/HYPOTHESES.jsonl",
    "?? .scratch/kol-writer-self-repair/",
    "?? output/live/book_b_live_allocation_facts_2026-08-23.json",
    "?? output/live/book_b_live_allocation_facts_2026-08-24.json",
    "?? output/live/book_b_live_allocation_facts_2026-08-25.json",
    "?? output/live/book_b_live_execution/",
    "?? output/live/book_b_live_freeze_2026-08-24.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-25.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-26.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-27.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-28.jsonl",
    "?? output/live/book_t_v1_control_receipt_2026-08-17.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-18.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-19.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-20.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-21.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-24.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-25.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-26.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-27.json"
  ]
}
```
