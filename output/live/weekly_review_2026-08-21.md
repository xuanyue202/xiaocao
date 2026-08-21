# 小草每周深度复盘 2026-08-21

## 先看结论
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个；另有 1 条本地工作区提醒，见下一节。

## 需要你看/确认的事项
- **需要确认** `short-selling-triple-gate-research-mapping-2026-08-21`：补齐跨市场做空三重门槛研究契约
- **本地工作区提醒，不是策略判断**：有 2 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/scripts/paper_record.py, tests/test_paper_record.py。

## 这批转录给我的启发
- **2026-08-20 review（2026-08-20_lv_xiaotong_review.json）**
  启发：吕晓彤在群主发言中称当前五架马车需要调齐，同时把做空限定为明显下跌、严重高估且可能持续下跌的高门槛动作；他还记录创新药、存储、三倍做空存储和小米的盘中分化，并反驳把宇树的二级市场高估值直接归因为上市收割。当前只沉淀做空的方向、估值、持续性三重确认纪律，所有资产和调仓指向仍需独立核验。
  姿态：not_applied_other_author：吕晓彤是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  打法：增加做空方向、估值、持续性三重确认的authority=0候选；不改确定性策略或实时风控。
  待验证：one_new_candidate：三重条件做空门槛，等待跨市场历史检验。
  命中审计：bound_to_current_image_evidence_sha256_820618d798a123788f63fba9ae297fcdc78c4f1700e7b83f1308e4556f2f853f
  工具缺口：构建跨市场做空候选的方向、估值和持续性联合门槛回测，禁止使用未核验的私人公司估值。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-08-20 2026-08-20_lv_xiaotong_review.json: not_applied_other_author：吕晓彤是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
- **Playbook/纪律**
  - 2026-08-20 2026-08-20_lv_xiaotong_review.json: 增加做空方向、估值、持续性三重确认的authority=0候选；不改确定性策略或实时风控。
- **候选假设**
  - 2026-08-20 2026-08-20_lv_xiaotong_review.json: one_new_candidate：三重条件做空门槛，等待跨市场历史检验。
- **命中审计**
  - 2026-08-20 2026-08-20_lv_xiaotong_review.json: bound_to_current_image_evidence_sha256_820618d798a123788f63fba9ae297fcdc78c4f1700e7b83f1308e4556f2f853f
- **工具/流程提案**
  - 2026-08-20 2026-08-20_lv_xiaotong_review.json: 构建跨市场做空候选的方向、估值和持续性联合门槛回测，禁止使用未核验的私人公司估值。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：1
- 自动落地候选数量：0

## 验证
- bash scripts/auto_daily.sh weekly: PASS (terminal weekly plan ready; run exactly once)
- weekly routed plan structure: PASS (1 proposal; 0 auto-apply candidates)
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src .venv/bin/python scripts/strategy_protocols.py --check: PASS (3 protocols)
- PYTHONPATH=src .venv/bin/python -m pytest tests/test_weekly_deep_review.py -q: PASS (14 passed)
- git diff --check: PASS

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 92 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-08-21/short-selling-triple-gate-research-mapping-2026-08-21.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 66,
    "candidate_assertions": 154,
    "candidate_to_tested": 0.11,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 92,
    "candidates_untested": 82,
    "dedup_ratio": 0.6,
    "instrumentation_todos": 35,
    "median_recurrence": 1.0,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 589,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 66
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 8,
  "pre_existing_dirty_sample": [
    " M kronos_screen/scripts/paper_record.py",
    " M tests/test_paper_record.py",
    "?? .scratch/kol-writer-self-repair/",
    "?? output/live/book_t_v1_control_receipt_2026-08-17.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-18.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-19.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-20.json",
    "?? output/live/book_t_v1_control_receipt_2026-08-21.json"
  ]
}
```
