# 小草每周深度复盘 2026-07-31

## 先看结论
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个；另有 1 条本地工作区提醒，见下一节。

## 需要你看/确认的事项
- **确认策略映射方案**：C_MODE_ROTATION_K_SURVIVORS 已经通过研究/纪律口径，但这次固定输入里还缺明确的落地映射、不过拟合说明或回滚方案。证据链补齐后可以自动落地；现在先写成提案，避免想当然改策略。
- **本地工作区提醒，不是策略判断**：有 34 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：.codex/skills/kol-intelligence/SKILL.md, .codex/skills/kol-intelligence/references/full-contract.md, .codex/skills/kol-intelligence/references/hourly-operation.md, kronos_screen/HYPOTHESES.jsonl, reference/experience/distill_action_log.jsonl；另有 29 个。

## 这批转录给我的启发
- **2026-07-27 盘前直播/早盘大师班（2026-07-27_xiaocao_morning.json）**
  启发：小草在7月27日早盘延续昨晚的轻仓框架：长鑫科技接近五倍开盘不值得赌，短线只把断板当娱乐仓，趋势低开可吸但必须做强不做弱；紫光股份、北方华创相对强，华虹公司不应低吸，ETF优先成交额更大的科创半导体ETF华夏588170。他给出约10点高位、11:15至11:30回调、下午修复的窗口，但强调跷跷板中高低点并不绝对，必须服从标的自身信号。分钟线支持强弱排序和时点窗口，收盘普涨则否定了把早盘随机轮动外推为全天弱市。
  姿态：no_change：早盘具体信号已在当日收盘后过期，且收盘广度已改变早盘结构，不由单场早盘覆盖全局posture。
  打法：保留‘钟点只作观察窗、标的信号优先’、‘同方向做强不做弱’与‘ETF先看流动性’三条authority=0先验。
  待验证：XH-041增加2026-07-27复现证据；新增标的信号优于固定钟点、同主题ETF高成交额降低执行损耗两个候选。
  命中审计：立新能源是老师与本地★KP/★M观察池重合但红断低吸COLD；本地实际★E/Book B为日科化学；金梅科技ASR未唯一映射。
  工具缺口：回放跷跷板日固定钟点、指数转折与标的信号，并建立同主题ETF流动性/滑点对照；不接真实交易。
- **2026-07-29 会员直播复盘（2026-07-29_lv_xiaotong_review.json）**
  启发：吕晓彤把人工智能类比互联网早期，判断科技长期牛市仍在；他认为AI存储需求仍强，但国产供给会在未来压低海外龙头利润率。对普通投资者，他优先选择宽基指数和核心资产，反对长期持有两倍、三倍单股产品，并把低置信资产换入高置信资产定义为组合调仓。可复用边界是长期方向、表达工具和风险预算必须分开。
  姿态：不直接更新小草A股现行posture；该来源是其他作者的跨市场长期判断，只作为产业、工具和组合方法先验。
  打法：补充长期方向、表达工具和风险预算三层分离，以及调仓按账户整体净值评估的方法。
  待验证：复现非杠杆长期科技工具假设，并新增存储分区利润、宽基降低淘汰风险、低置信资产调仓三条候选。
  命中审计：完整逐字稿193段逐段覆盖，名人录音与三到五年预测保留为未核实转述；源视频未在协调器本地下载。
  工具缺口：跟踪QQQ/TQQQ路径差、长鑫产能与海外存储毛利率、科技恐慌窗口中的宽基和单股永久损失率。
- **2026-07-29 盘后复盘/大师班专场（2026-07-29_xiaocao_review.json）**
  启发：小草把7月29日定义为弱修复：上涨家数很多，但赚钱效应、主线强度和大市值科技承接仍不足。趋势科技经历重挫与套牢后需要时间消化，不能因为跌深就抢反弹；小市值短线情绪有所改善，但仍须等待环境、方向和模式共同确认。复盘还强调A股最小交易单位会让小账户被动重仓，买入数量本身就是风险控制的一部分。
  姿态：no_change：现行posture已过期，本场是短效复盘且次日仍需盘面确认，不用单场口播覆盖全局posture。
  打法：保留‘普涨不等于高质量修复’、‘跌深不等于买点’和‘最小交易单位也是仓位约束’三条authority=0先验。
  待验证：XH-033增加2026-07-29复现证据；新增修复质量和最小交易单位被动集中两个候选。
  命中审计：老师点名仅为情绪或趋势观察；本地7月30日★E久其软件、创新医疗均未被老师点名，没有精确策略命中。
  工具缺口：回放普涨但无主线日的追涨质量，并按一手占净值比例研究小账户组合左尾；不接真实交易。
- **2026-07-30 盘前直播/早盘大师班（2026-07-30_xiaocao_morning.json）**
  启发：小草在7月30日盘前没有选出合格的自有或专享模式，明确把‘绿盘低吸/首断低吸娱乐一下’限定为有条件例外，而非正式推荐。盘面方向分散、科技继续轮动走低，短线情绪和连板亏钱效应边际缓和，但仍应等待真正冰点后风向标能否承接，不做第一个吃螃蟹的人。
  姿态：no_change：盘前具体信号已被日内现实覆盖，且现行posture文件已过期，不用单场盘前口播覆盖全局状态。
  打法：保留‘绝对门槛先于相对排序’、‘无模式也是完整决策’和‘冰点先看风向标承接’三条authority=0先验。
  待验证：XH-033增加2026-07-30复现证据；新增无入围时主动空仓、情绪风向标承接领先短线修复两个候选。
  命中审计：艾艾精工、恒尚节能、金牛化工和爱丽家居仅为情绪观察；本地★E久其软件、创新医疗均未被老师点名，没有精确策略命中。
  工具缺口：回放无入围日的空仓与强选最高分，并研究情绪风向标连续承接对后续短线模式胜率的领先性；不接真实交易。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-07-27 2026-07-27_xiaocao_morning.json: no_change：早盘具体信号已在当日收盘后过期，且收盘广度已改变早盘结构，不由单场早盘覆盖全局posture。
  - 2026-07-29 2026-07-29_lv_xiaotong_review.json: 不直接更新小草A股现行posture；该来源是其他作者的跨市场长期判断，只作为产业、工具和组合方法先验。
  - 2026-07-29 2026-07-29_xiaocao_review.json: no_change：现行posture已过期，本场是短效复盘且次日仍需盘面确认，不用单场口播覆盖全局posture。
  - 2026-07-30 2026-07-30_xiaocao_morning.json: no_change：盘前具体信号已被日内现实覆盖，且现行posture文件已过期，不用单场盘前口播覆盖全局状态。
- **Playbook/纪律**
  - 2026-07-27 2026-07-27_xiaocao_morning.json: 保留‘钟点只作观察窗、标的信号优先’、‘同方向做强不做弱’与‘ETF先看流动性’三条authority=0先验。
  - 2026-07-29 2026-07-29_lv_xiaotong_review.json: 补充长期方向、表达工具和风险预算三层分离，以及调仓按账户整体净值评估的方法。
  - 2026-07-29 2026-07-29_xiaocao_review.json: 保留‘普涨不等于高质量修复’、‘跌深不等于买点’和‘最小交易单位也是仓位约束’三条authority=0先验。
  - 2026-07-30 2026-07-30_xiaocao_morning.json: 保留‘绝对门槛先于相对排序’、‘无模式也是完整决策’和‘冰点先看风向标承接’三条authority=0先验。
- **候选假设**
  - 2026-07-27 2026-07-27_xiaocao_morning.json: XH-041增加2026-07-27复现证据；新增标的信号优于固定钟点、同主题ETF高成交额降低执行损耗两个候选。
  - 2026-07-29 2026-07-29_lv_xiaotong_review.json: 复现非杠杆长期科技工具假设，并新增存储分区利润、宽基降低淘汰风险、低置信资产调仓三条候选。
  - 2026-07-29 2026-07-29_xiaocao_review.json: XH-033增加2026-07-29复现证据；新增修复质量和最小交易单位被动集中两个候选。
  - 2026-07-30 2026-07-30_xiaocao_morning.json: XH-033增加2026-07-30复现证据；新增无入围时主动空仓、情绪风向标承接领先短线修复两个候选。
- **命中审计**
  - 2026-07-27 2026-07-27_xiaocao_morning.json: 立新能源是老师与本地★KP/★M观察池重合但红断低吸COLD；本地实际★E/Book B为日科化学；金梅科技ASR未唯一映射。
  - 2026-07-29 2026-07-29_lv_xiaotong_review.json: 完整逐字稿193段逐段覆盖，名人录音与三到五年预测保留为未核实转述；源视频未在协调器本地下载。
  - 2026-07-29 2026-07-29_xiaocao_review.json: 老师点名仅为情绪或趋势观察；本地7月30日★E久其软件、创新医疗均未被老师点名，没有精确策略命中。
  - 2026-07-30 2026-07-30_xiaocao_morning.json: 艾艾精工、恒尚节能、金牛化工和爱丽家居仅为情绪观察；本地★E久其软件、创新医疗均未被老师点名，没有精确策略命中。
- **工具/流程提案**
  - 2026-07-27 2026-07-27_xiaocao_morning.json: 回放跷跷板日固定钟点、指数转折与标的信号，并建立同主题ETF流动性/滑点对照；不接真实交易。
  - 2026-07-29 2026-07-29_lv_xiaotong_review.json: 跟踪QQQ/TQQQ路径差、长鑫产能与海外存储毛利率、科技恐慌窗口中的宽基和单股永久损失率。
  - 2026-07-29 2026-07-29_xiaocao_review.json: 回放普涨但无主线日的追涨质量，并按一手占净值比例研究小账户组合左尾；不接真实交易。
  - 2026-07-30 2026-07-30_xiaocao_morning.json: 回放无入围日的空仓与强选最高分，并研究情绪风向标连续承接对后续短线模式胜率的领先性；不接真实交易。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：1
- 自动落地候选数量：5

## 验证
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src python3 scripts/weekly_deep_review.py --help: PASS
- PYTHONPATH=src python3 scripts/strategy_protocols.py --check: PASS (2 protocols)
- python3 -m json.tool output/live/weekly_plan_2026-07-31.json: PASS
- PYTHONPATH=src python3 -m pytest tests/test_weekly_deep_review.py tests/test_flywheel_sweep.py -q: PASS (16 passed)

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：blocked；待处理 PASS=['C_mode_rotation_k_survivors']
- 知识飞轮：候选 65 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-07-31/pass-pending-c_mode_rotation_k_survivors.md
- .scratch/weekly-deep-review/2026-07-31/instrumentation-deferred-batch.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 42,
    "candidate_assertions": 111,
    "candidate_to_tested": 0.15,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 65,
    "candidates_untested": 55,
    "dedup_ratio": 0.59,
    "instrumentation_todos": 11,
    "median_recurrence": 1,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 568,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 42
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 34,
  "pre_existing_dirty_sample": [
    " M .codex/skills/kol-intelligence/SKILL.md",
    " M .codex/skills/kol-intelligence/references/full-contract.md",
    " M .codex/skills/kol-intelligence/references/hourly-operation.md",
    " M kronos_screen/HYPOTHESES.jsonl",
    " M reference/experience/distill_action_log.jsonl",
    " M reference/experience/distilled/2026-07-13_lv_xiaotong_review.json",
    " M reference/experience/distilled/2026-07-16_xiaocao_review.json",
    " M reference/experience/xiaocao_hypotheses.jsonl",
    " M scripts/kol_daily.py",
    " M src/xiaocao/kol/daily.py",
    " M src/xiaocao/kol/decisions.py",
    " M src/xiaocao/kol/enrichment_types.py",
    " M src/xiaocao/kol/initial_import.py",
    " M src/xiaocao/kol/lv_subscription.py",
    " M src/xiaocao/kol/publication.py",
    " M src/xiaocao/kol/reader_copy.py",
    " M src/xiaocao/kol/reader_copy_correction.py",
    " M src/xiaocao/kol/subscription_video.py",
    " M src/xiaocao/kol/xiaocao_live.py",
    " M tests/test_kol_daily.py"
  ]
}
```
