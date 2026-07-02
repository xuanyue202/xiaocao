# 小草每周深度复盘 2026-07-03

## 先看结论
- 本周模式：本周无需动作（`NO_ACTION_REQUIRED`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：0 个，见下一节。

## 需要你看/确认的事项
- 没有需要你确认的事项。

## 这批转录给我的启发
- **2026-07-01 盘前直播（2026-07-01_morning.json）**
  启发：7/1 盘前延续 6/30 的 trend_tail_rotation：电子/半导体/存储仍是赚钱所在，趋势股多数还在趋势线内，但行情已经从主线单边最强进入补涨、高低切和可能的加速尾声。小草强调趋势股沿趋势线/5日线处理，不能看到点名票就追；存储/半导体/元器件/CPO 仍是核心方向，能做科创/20cm 则优先科创/20cm，其次创业板，再其次主板。短线仍以趋势为主框架下的模式化参与为主，9:35 前模式内下杀可以吸，追涨要克制。
  姿态：7/1 早盘延续 trend_tail_rotation：电子/半导体主线还没死，但已经进入补涨、加速尾声和高低切窗口；处理上用5日线兜底，修复反弹偏减仓。
  打法：校准“板块内高低切”：早期主线轮涨可以持有，尾声阶段高位核心弱、低中位补涨反而是扩散减仓信号；新增看不懂时退回5日线的兜底规则。
  待验证：把 XH-038、XH-025 记为再次出现；新增“同一电子主线内，科创/20cm 的尾声补涨弹性是否优于主板10cm”的候选假设。
- **2026-07-01 盘后复盘/大师班专场（2026-07-01_review.json）**
  启发：7/1 盘后复盘把当天的科技回调定义为高低切/跷跷板中的正常波动，而不是存储芯片和科技主线彻底结束。核心动作是：趋势股破5日线走，没破不乱动；如果次日修复，仍可在反弹里减仓；当前不适合机械去弱留强，而更接近轻仓低吸高抛。小草反复区分 6/22 那种外部旧方向主动带起、科技被动弱反弹的卖点，和 7/1 这种科技内部仍强、只是高低切/扩散的减仓窗口。复盘还明确了系统使用的元规则：行情结构变了，同一套工具要切换用法；看不懂主动/被动，就退回…
  姿态：把当前姿态更新为 2026-07-01：trend_tail_rotation 被复盘确认，有效期到 2026-07-03；动作是修复减仓、5日线兜底、高低切阶段轻仓低吸高抛。
  打法：新增 2026-07-01 校准：板块内高低切必须看阶段，不能把 6/17 那种健康轮涨直接套到尾声扩散；尾声扩散要减仓而不是继续追强。
  待验证：把 XH-038、XH-025 记为再次出现；新增“高低切环境里，大涨次日追涨是否不如回调/下杀后的模式内低吸”的候选假设。
  命中审计：7/1 命中审计：信濠光电是真正的老师样本与本地正式买入重合；传艺科技是本地买入标杆但不是老师点名重合；海川智能/拓斯达只是 authority=0 的观察 cohort；多数趋势核心只是方向样本，不能算短线命中。
  工具缺口：implemented: scripts/strategy_hit_audit.py 已补 strategy-hit-audit 投影工具，把 recommend、signal、positions、cohorts 聚合成可读表，避免未来每次复盘手动扒 JSON。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-07-01 2026-07-01_morning.json: 7/1 早盘延续 trend_tail_rotation：电子/半导体主线还没死，但已经进入补涨、加速尾声和高低切窗口；处理上用5日线兜底，修复反弹偏减仓。
  - 2026-07-01 2026-07-01_review.json: 把当前姿态更新为 2026-07-01：trend_tail_rotation 被复盘确认，有效期到 2026-07-03；动作是修复减仓、5日线兜底、高低切阶段轻仓低吸高抛。
- **Playbook/纪律**
  - 2026-07-01 2026-07-01_morning.json: 校准“板块内高低切”：早期主线轮涨可以持有，尾声阶段高位核心弱、低中位补涨反而是扩散减仓信号；新增看不懂时退回5日线的兜底规则。
  - 2026-07-01 2026-07-01_review.json: 新增 2026-07-01 校准：板块内高低切必须看阶段，不能把 6/17 那种健康轮涨直接套到尾声扩散；尾声扩散要减仓而不是继续追强。
- **候选假设**
  - 2026-07-01 2026-07-01_morning.json: 把 XH-038、XH-025 记为再次出现；新增“同一电子主线内，科创/20cm 的尾声补涨弹性是否优于主板10cm”的候选假设。
  - 2026-07-01 2026-07-01_review.json: 把 XH-038、XH-025 记为再次出现；新增“高低切环境里，大涨次日追涨是否不如回调/下杀后的模式内低吸”的候选假设。
- **命中审计**
  - 2026-07-01 2026-07-01_review.json: 7/1 命中审计：信濠光电是真正的老师样本与本地正式买入重合；传艺科技是本地买入标杆但不是老师点名重合；海川智能/拓斯达只是 authority=0 的观察 cohort；多数趋势核心只是方向样本，不能算短线命中。
- **工具/流程提案**
  - 2026-07-01 2026-07-01_review.json: implemented: scripts/strategy_hit_audit.py 已补 strategy-hit-audit 投影工具，把 recommend、signal、positions、cohorts 聚合成可读表，避免未来每次复盘手动扒 JSON。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, git status --porcelain
- 提案数量：0
- 自动落地候选数量：0

## 验证
- PYTHONPATH=src python3 -m pytest -q: PASS (510 passed, 8 skipped; pandas-dependent branches skipped)
- python3 -m py_compile scripts/strategy_hit_audit.py scripts/weekly_deep_review.py scripts/flywheel_selfcheck.py: PASS
- bash -n scripts/auto_daily.sh: PASS
- python3 scripts/package_xiaocao_skill.py: PASS

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
  "scoreboard": {},
  "pass_evidence": [],
  "pre_existing_dirty_count": 0,
  "pre_existing_dirty_sample": []
}
```
