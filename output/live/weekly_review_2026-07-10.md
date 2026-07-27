# 小草每周深度复盘 2026-07-10

## 先看结论
- 本周模式：本周无需动作（`NO_ACTION_REQUIRED`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：0 个；另有 1 条本地工作区提醒，见下一节。

## 需要你看/确认的事项
- **本地工作区提醒，不是策略判断**：有 32 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：.codex/skills/xiaocao-trading/SKILL.md, docs/FLYWHEEL.md, docs/OPERATING_CONTRACT.md, docs/STRATEGY_EVOLUTION_PROTOCOL.md, kronos_screen/HYPOTHESES.jsonl；另有 27 个。

## 这批转录给我的启发
- 本周没有新的高信号转录启发。

## 已经改进/沉淀到哪里
- 没有新的知识层变更。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：0
- 自动落地候选数量：0

## 验证
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src python3 -m pytest tests/test_weekly_deep_review.py tests/test_flywheel_sweep.py -q: PASS (16 passed)

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 41 / 已测 10 / 已退役 5 / 最老未测 2026-06-01

## 提案文件
- none

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 32,
    "candidate_assertions": 79,
    "candidate_to_tested": 0.24,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 41,
    "candidates_untested": 31,
    "dedup_ratio": 0.52,
    "instrumentation_todos": 1,
    "median_recurrence": 2,
    "oldest_untested": "2026-06-01",
    "oldest_untested_age_days": 39,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 32
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 35,
  "pre_existing_dirty_sample": [
    " M .codex/skills/xiaocao-trading/SKILL.md",
    " M .gitignore",
    " M README.md",
    " M docs/FLYWHEEL.md",
    " M docs/OPERATING_CONTRACT.md",
    " M kronos_screen/HYPOTHESES.jsonl",
    " M kronos_screen/scripts/kronos_lib.py",
    " M reference/experience/README.md",
    " M scripts/auto_daily.sh",
    " M scripts/build_context_pack.py",
    " M scripts/flywheel_sweep.py",
    " M scripts/research_run.py",
    " M scripts/weekly_deep_review.py",
    " M src/xiaocao/cli.py",
    " M src/xiaocao/live/context_pack.py",
    " M src/xiaocao/strategy/adaptive.py",
    " M src/xiaocao/strategy/explain.py",
    " M src/xiaocao/strategy/regime.py",
    " M src/xiaocao/strategy/rules.py",
    " M src/xiaocao/strategy/runner.py"
  ]
}
```
