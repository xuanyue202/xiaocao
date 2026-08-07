# 小草每周深度复盘 2026-08-07

## 先看结论
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个，见下一节。

## 需要你看/确认的事项
- **确认策略映射方案**：C_MODE_ROTATION_K_SURVIVORS 已经通过研究/纪律口径，但这次固定输入里还缺明确的落地映射、不过拟合说明或回滚方案。证据链补齐后可以自动落地；现在先写成提案，避免想当然改策略。

## 这批转录给我的启发
- **2026-08-06 微信公众号复盘（2026-08-06_liu_shao_review.json）**
  启发：刘少狙击营认为非农数据公布前市场更可能维持横盘，8月宏观环境好于7月，半导体整体仍偏多；文章同时用7月量化多头产品普遍回撤说明极端市场并非只有普通投资者受损，并把注意力重新放回自身交易纪律。作者还以纳指、未明确指代的‘老毛’和冰糖橙现货说明长期持有资产可按个人生活目标分工，但这些个人样本不是直接买入建议。
  姿态：不应用：刘少狙击营是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  打法：候选补充：不可证伪的市场归因不应替代自身风险管理；长期持有的个人角色分工不能直接外推为买入规则。
  待验证：no_change：本文数据未独立核验，个人配置样本不足以新增统计假设。
  命中审计：完整公众号正文及唯一装饰图片均已覆盖，证据绑定SHA-256 a060f9904a48ee1a7a5911e7a38ce482c032946a078f856d3d5fbf26ba8ef3dc。
  工具缺口：no_issue_created：后续只在更多独立样本中观察机构亏损归因与个人资产角色分工是否具有稳定决策价值。
- **2026-08-06 公开直播复盘（2026-08-06_lv_xiaotong_review.json）**
  启发：吕晓彤把人工智能、机器人和商业航天视为三至五年甚至更长周期的科技方向，但同时承认科技估值风险已经存在，资金期限必须与持有期匹配。存储方面，他认为短期利润率、长协和充分预期使业绩缺少惊喜，长期需求则取决于物理人工智能扩散；这不是无条件买入。直播还给出三条可复用的风险边界：储蓄险要先看流动性与保证程度，投资者无法克服人性时先控制仓位并拒绝杠杆，成熟汽车行业集中后独立供应商可能被整车厂自研挤压。
  姿态：不应用：吕晓彤属于其他作者；现行小草posture已过期，本材料只写authority=0知识，不修改posture_current或REGIME_TIMELINE。
  打法：候选补充资金期限、预期差、保证与非保证收益、行业集中和仓位生存五层分离。
  待验证：复用XH-070与XH-079的原文主张以合并来源日期；新增汽车自研替代与储蓄险流动性两条authority=0候选。
  命中审计：完整逐字稿40503字符、290个稳定语义段逐段覆盖；作者酒后状态、个人一级市场利益关系和无法识别的行业均保留为边界。
  工具缺口：跟踪人工智能和存储预期差、汽车供应商客户集中与毛利率，并建立储蓄险保证现金价值和流动性压力测试。
- **2026-08-06 盘前大师班直播（2026-08-06_xiaocao_morning.json）**
  启发：小草在8月6日9:20至9:31把市场定义为短线边际转暖但仍偏轮动：高位与中位股分化时，普通参与者优先选择低位首板断板，不急于中高位断板；竞价与盘中模式都可观察，盘中弱转强、卡位和对比可能在9:25之后才取得资格，不能用收盘赢家倒推竞价必选。趋势抱团加小涨幅属于红盘或盘中起爆追涨，不是低吸。组合上，他建议第一、第二名两只平铺以降低单票波动，同时提醒标的过多会超出普通人的控制能力。当天生产系统的首红断和绿断模式均为ACTIVE，并按自身…
  姿态：no_change：短线转暖判断只得到同日模式资格和个别样本支持，收盘仍有显著单票分化，不用单场盘前直播覆盖长期posture_current。
  打法：保留‘资格随时点变化、禁止收盘后见之明’、‘低位首板优先于中高位断板’和‘固定总风险预算下比较前二平铺’三条authority=0先验。
  待验证：新增位置层级、盘中动态资格和前二等权三条authority=0候选，等待研究护栏。
  命中审计：完整逐字稿4876字符、39个稳定语义段；核对8月6日9:28推荐、9:32纸面成交、15:00两只Book B持仓与15:20市场姿态。
  工具缺口：记录首次资格时间与位置层级；在固定总仓位下比较第一名和前二等权，不接真实交易。
- **2026-08-06 晚间大师班复盘（2026-08-06_xiaocao_review.json）**
  启发：小草在8月6日晚把盘面定义为短线情绪继续改善、趋势侧仍偏缩量轮动。普通参与者仍优先首板断板和绿盘低吸，不把高位龙头、红盘起爆或二板以上追涨当作默认动作；若次日高标断板没有一字跌停、连板梯队与负反馈稳定，可观察中高位断板，否则退回首板断板。AI硬件同时具备趋势容量、三至四板连板梯队和断板反包，成为主要观察链，但他预期连续走强后先出现分歧，再比较龙头强弱。仓位口径为三至四成滚动，示例是两成底仓加滚动到四成。当天本地确定性系统独立买入的恒银…
  姿态：no_change：现行posture已过期，但单场晚间复盘和次日上午局部证据不足以重写全局posture_current。
  打法：确认渐进切换、低位优先、盘中动态资格三条现有authority=0先验，并新增趋势核心与连板梯队双证据候选。
  待验证：复用XH-075、XH-076、XH-077的原文主张以合并来源日期；新增AI硬件双证据结构假设，等待研究护栏。
  命中审计：完整逐字稿22657字符、163个稳定语义段；只读核对8月6日本地推荐、信号和纸面成交以及8月7日9:28推荐和10:57持仓。
  工具缺口：前向记录题材趋势核心相对强弱、梯队层数、分歧后修复、首次盘中资格和固定风险仓位。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-08-06 2026-08-06_liu_shao_review.json: 不应用：刘少狙击营是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  - 2026-08-06 2026-08-06_lv_xiaotong_review.json: 不应用：吕晓彤属于其他作者；现行小草posture已过期，本材料只写authority=0知识，不修改posture_current或REGIME_TIMELINE。
  - 2026-08-06 2026-08-06_xiaocao_morning.json: no_change：短线转暖判断只得到同日模式资格和个别样本支持，收盘仍有显著单票分化，不用单场盘前直播覆盖长期posture_current。
  - 2026-08-06 2026-08-06_xiaocao_review.json: no_change：现行posture已过期，但单场晚间复盘和次日上午局部证据不足以重写全局posture_current。
- **Playbook/纪律**
  - 2026-08-06 2026-08-06_liu_shao_review.json: 候选补充：不可证伪的市场归因不应替代自身风险管理；长期持有的个人角色分工不能直接外推为买入规则。
  - 2026-08-06 2026-08-06_lv_xiaotong_review.json: 候选补充资金期限、预期差、保证与非保证收益、行业集中和仓位生存五层分离。
  - 2026-08-06 2026-08-06_xiaocao_morning.json: 保留‘资格随时点变化、禁止收盘后见之明’、‘低位首板优先于中高位断板’和‘固定总风险预算下比较前二平铺’三条authority=0先验。
  - 2026-08-06 2026-08-06_xiaocao_review.json: 确认渐进切换、低位优先、盘中动态资格三条现有authority=0先验，并新增趋势核心与连板梯队双证据候选。
- **候选假设**
  - 2026-08-06 2026-08-06_liu_shao_review.json: no_change：本文数据未独立核验，个人配置样本不足以新增统计假设。
  - 2026-08-06 2026-08-06_lv_xiaotong_review.json: 复用XH-070与XH-079的原文主张以合并来源日期；新增汽车自研替代与储蓄险流动性两条authority=0候选。
  - 2026-08-06 2026-08-06_xiaocao_morning.json: 新增位置层级、盘中动态资格和前二等权三条authority=0候选，等待研究护栏。
  - 2026-08-06 2026-08-06_xiaocao_review.json: 复用XH-075、XH-076、XH-077的原文主张以合并来源日期；新增AI硬件双证据结构假设，等待研究护栏。
- **命中审计**
  - 2026-08-06 2026-08-06_liu_shao_review.json: 完整公众号正文及唯一装饰图片均已覆盖，证据绑定SHA-256 a060f9904a48ee1a7a5911e7a38ce482c032946a078f856d3d5fbf26ba8ef3dc。
  - 2026-08-06 2026-08-06_lv_xiaotong_review.json: 完整逐字稿40503字符、290个稳定语义段逐段覆盖；作者酒后状态、个人一级市场利益关系和无法识别的行业均保留为边界。
  - 2026-08-06 2026-08-06_xiaocao_morning.json: 完整逐字稿4876字符、39个稳定语义段；核对8月6日9:28推荐、9:32纸面成交、15:00两只Book B持仓与15:20市场姿态。
  - 2026-08-06 2026-08-06_xiaocao_review.json: 完整逐字稿22657字符、163个稳定语义段；只读核对8月6日本地推荐、信号和纸面成交以及8月7日9:28推荐和10:57持仓。
- **工具/流程提案**
  - 2026-08-06 2026-08-06_liu_shao_review.json: no_issue_created：后续只在更多独立样本中观察机构亏损归因与个人资产角色分工是否具有稳定决策价值。
  - 2026-08-06 2026-08-06_lv_xiaotong_review.json: 跟踪人工智能和存储预期差、汽车供应商客户集中与毛利率，并建立储蓄险保证现金价值和流动性压力测试。
  - 2026-08-06 2026-08-06_xiaocao_morning.json: 记录首次资格时间与位置层级；在固定总仓位下比较第一名和前二等权，不接真实交易。
  - 2026-08-06 2026-08-06_xiaocao_review.json: 前向记录题材趋势核心相对强弱、梯队层数、分歧后修复、首次盘中资格和固定风险仓位。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：1
- 自动落地候选数量：13

## 验证
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src .venv/bin/python scripts/strategy_protocols.py --check: PASS (2 protocols)
- PYTHONPATH=src .venv/bin/python -m pytest tests/test_weekly_deep_review.py -q: PASS (11 passed)

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：blocked；待处理 PASS=['C_mode_rotation_k_survivors']
- 知识飞轮：候选 84 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-08-07/pass-pending-c_mode_rotation_k_survivors.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 56,
    "candidate_assertions": 136,
    "candidate_to_tested": 0.12,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 84,
    "candidates_untested": 74,
    "dedup_ratio": 0.62,
    "instrumentation_todos": 25,
    "median_recurrence": 1.0,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 575,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 56
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 2,
  "pre_existing_dirty_sample": [
    "?? output/live/.cutover-backups/",
    "?? output/weixin-articles/"
  ]
}
```
