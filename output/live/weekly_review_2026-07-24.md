# 小草每周深度复盘 2026-07-24

## 先看结论
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个；另有 1 条本地工作区提醒，见下一节。

## 需要你看/确认的事项
- **确认策略映射方案**：C_MODE_ROTATION_K_SURVIVORS 已经通过研究/纪律口径，但这次固定输入里还缺明确的落地映射、不过拟合说明或回滚方案。证据链补齐后可以自动落地；现在先写成提案，避免想当然改策略。
- **本地工作区提醒，不是策略判断**：有 79 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：.codex/automations/xiaocao-daily-eod/automation.toml, .codex/automations/xiaocao-daily-morning-execution/, .codex/automations/xiaocao-daily-morning/automation.toml, .codex/automations/xiaocao-intraday-monitor-05/automation.toml, .codex/automations/xiaocao-intraday-monitor-1455/automation.toml；另有 74 个。

## 这批转录给我的启发
- **2026-07-21 盘后复盘/大师班专场（2026-07-21_xiaocao_review.json）**
  启发：小草把7月21日早盘半导体深跌、融资盘集中出清和盘中V形反转视为前一日风险判断的加速完成，但明确反弹不会一蹴而就：首日大涨后仍有套牢盘与获利盘，执行上应等待回调/分歧而不是追高。当前只关注趋势大票和科创半导体；不能交易科创个股可观察科创芯片ETF 588750.XSHG。7月22日必须重新比较科技内部强度，半导体若不再最强则撤销计划；趋势仓上限为两到三成，短线情绪股继续等待。课程与软件销售内容不构成交易证据。
  姿态：not_applied：本场方向必须在2026-07-22早盘重新验证，且现行posture虽已过期，也不应由单场复盘直接覆盖；先保留为authority=0的短效候选。
  打法：记录‘融资盘出清不等于追首阳’、‘强度逐日重算’和‘趋势修复不外推到短线情绪’三条判断先验；未直接修改确定性脊柱或参数。
  待验证：XH-041与XH-036各增加2026-07-21复现证据；新增‘更低价格处第二次预警更强可识别拐点’的authority=0候选。
  命中审计：not_applicable：本场明确说短线情绪股继续等待；点名个股属于趋势/强弱教学例，不作为老师短线赢家与本地9:25信号做伪重合。
  工具缺口：为盘中重复预警建立shadow回放，按单次、重复不增强、低价增强三组比较后续收益和最大不利变动；不接真实交易接口。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-07-21 2026-07-21_xiaocao_review.json: not_applied：本场方向必须在2026-07-22早盘重新验证，且现行posture虽已过期，也不应由单场复盘直接覆盖；先保留为authority=0的短效候选。
- **Playbook/纪律**
  - 2026-07-21 2026-07-21_xiaocao_review.json: 记录‘融资盘出清不等于追首阳’、‘强度逐日重算’和‘趋势修复不外推到短线情绪’三条判断先验；未直接修改确定性脊柱或参数。
- **候选假设**
  - 2026-07-21 2026-07-21_xiaocao_review.json: XH-041与XH-036各增加2026-07-21复现证据；新增‘更低价格处第二次预警更强可识别拐点’的authority=0候选。
- **命中审计**
  - 2026-07-21 2026-07-21_xiaocao_review.json: not_applicable：本场明确说短线情绪股继续等待；点名个股属于趋势/强弱教学例，不作为老师短线赢家与本地9:25信号做伪重合。
- **工具/流程提案**
  - 2026-07-21 2026-07-21_xiaocao_review.json: 为盘中重复预警建立shadow回放，按单次、重复不增强、低价增强三组比较后续收益和最大不利变动；不接真实交易接口。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：1
- 自动落地候选数量：1

## 验证
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src python3 scripts/weekly_deep_review.py --help: PASS
- PYTHONPATH=src python3 scripts/strategy_protocols.py --check: PASS (2 protocols)
- python3 -m json.tool output/live/weekly_plan_2026-07-24.json: PASS
- PYTHONPATH=src python3 -m pytest tests/test_weekly_deep_review.py tests/test_flywheel_sweep.py -q: PASS (16 passed)

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：blocked；待处理 PASS=['C_mode_rotation_k_survivors']
- 知识飞轮：候选 51 / 已测 10 / 已退役 5 / 最老未测 2026-06-01

## 提案文件
- .scratch/weekly-deep-review/2026-07-24/pass-pending-c_mode_rotation_k_survivors.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 36,
    "candidate_assertions": 91,
    "candidate_to_tested": 0.2,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 51,
    "candidates_untested": 41,
    "dedup_ratio": 0.56,
    "instrumentation_todos": 5,
    "median_recurrence": 1,
    "oldest_untested": "2026-06-01",
    "oldest_untested_age_days": 53,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 36
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 113,
  "pre_existing_dirty_sample": [
    " M .codex/automations/xiaocao-daily-eod/automation.toml",
    " M .codex/automations/xiaocao-daily-morning/automation.toml",
    " M .codex/automations/xiaocao-intraday-monitor-05/automation.toml",
    " M .codex/automations/xiaocao-intraday-monitor-1455/automation.toml",
    " M .codex/automations/xiaocao-intraday-monitor/automation.toml",
    " M .codex/automations/xiaocao-intraday-risk-precheck-1425/automation.toml",
    " M .codex/automations/xiaocao-weekly-deep-review/automation.toml",
    " M .codex/skills/kol-intelligence/SKILL.md",
    " M .codex/skills/xiaocao-trading/SKILL.md",
    " M AGENTS.md",
    " M README.md",
    " M docs/FLYWHEEL.md",
    " M docs/OPERATING_CONTRACT.md",
    " M docs/codex_skill_maintenance.md",
    " M kronos_screen/HYPOTHESES.jsonl",
    " M kronos_screen/scripts/capture_signals.py",
    " M kronos_screen/scripts/forward_eval.py",
    " M kronos_screen/scripts/kronos_lib.py",
    " M kronos_screen/scripts/paper_record.py",
    " M output/live/flywheel_change_ledger.jsonl"
  ]
}
```
