# 小草每周深度复盘 2026-08-14

## 先看结论
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个；另有 1 条本地工作区提醒，见下一节。

## 需要你看/确认的事项
- **补齐工具实施映射**：固定输入允许工具类 `AUTO_APPLIED`，但这 8 条只有方向性 todo；缺少逐项数据源、字段、目标和夹具时自动写代码会把未解决的研究问题误报成已落地。本周因此只给提案；确认后优先映射已有生产事实源的执行纪律/命中审计项。
- **本地工作区提醒，不是策略判断**：有 1 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl。

## 这批转录给我的启发
- **2026-08-10 盘前大师班（2026-08-10_xiaocao_morning.json）**
  启发：小草把8月10日盘前与开盘初段定义为指数跷跷板下的轮动环境，而非一致主升：仓位应按轮动阶段控制，连续上涨的AI硬件趋势大票未来两天存在回调风险；龙头卡位不清晰时回到断板、人气股低吸等模式，不围绕盘前排名追涨。执行节奏是反弹可高抛、回调只按模式和承接重新验证。收盘核对显示全市场上涨3968家，但上证上涨、创业板和科创50下跌，支持广度偏强与风格分化并存；点名股票表现高度分化，因此盘前排名不能延续成收盘后的订单。该场材料复现已有轮动仓位、…
  姿态：no_change：现行全局posture已过期，单场盘前材料与单日收盘核对不足以安全覆盖全局姿态；当前建议仅留在已发布决策审计。
  打法：no_change：轮动仓位、标的自身信号优先、广度不能单独开放追涨已在现有playbook和候选中表达。
  待验证：复现XH-054、XH-059和XH-075，增加2026-08-10小草来源绑定；authority=0，不改确定性参数。
  命中审计：完整逐字稿2695字符、22段，开中尾审计通过；8月10日收盘上涨3968家、下跌1391家，上证与创业板/科创50方向分化。
  工具缺口：继续前向记录跷跷板日标的自身信号、广度与主线集中度、分档仓位路径；禁止用收盘赢家回填盘前命中。
- **2026-08-10 晚间大师班复盘（2026-08-10_xiaocao_review.json）**
  启发：小草在8月10日晚间复盘中延续早间的轮动判断，并把8月11日来源风险预算量化为10%：若环境和模式资格同时允许，人气股低吸与首断低吸各分配5%；追涨和打板不做，前一涨停为一字板的首断对象排除。趋势大票仍有继续回调可能，中际旭创、通宇通讯偏弱，胜宏科技、工业富联、天孚通信、长电科技仅作相对强弱案例。收盘核对支持指数和AI硬件核心分化，但不证明市场进入主升，也不把点名股升级为盘后订单。可复用部分是环境到风险预算、再到模式分配和形态排除的决…
  姿态：no_change：现行全局posture已过期，单场晚间复盘与单日收盘事实不足以安全覆盖全局姿态；只保留当期决策和authority=0先验。
  打法：no_change：环境到分档仓位的链已由现有轮动纪律表达；一字板首断排除先进入候选研究，不直接写入确定性playbook。
  待验证：复现XH-075并增加8月10日晚间来源绑定；新增‘一字板前置首断可能弱于实体板’候选，全部authority=0。
  命中审计：完整逐字稿8310字符、127行，SHA-256为7b6469d1...c5e3；64个投资语义片段逐段覆盖；8月10日收盘指数、AI硬件核心和高标案例已核对，本地推荐与Book记录分账。
  工具缺口：前向记录午后修复幅度与次日低吸赔率、轮动仓位档位、首断前一涨停形态、实际可成交性和左尾；禁止用盘后赢家回填盘前命中。
- **2026-08-11 晚间大师班复盘（2026-08-11_xiaocao_review.json）**
  启发：小草在8月11日晚间把市场概括为‘趋势搭台、短线主导’：权重和趋势大票没有一致领涨，医药、人气与连板等短线模式提供局部弹性；趋势可能回调消化后再修复，但不能守着随机腰斩股等回本。方法重点从选股推进到执行分层：高位接力只适合能实时止损的人，不封板就走；求稳者使用评分合格的低位、低开或超跌低吸，可分散两三只，但最多容错两三天，ST排除。8月11日收盘广度偏弱、指数分化且来源案例涨跌并存，支持结构分化，不验证直播赢家或多年稳定收益。全部au…
  姿态：no_change：现行全局posture已过期39天，单场晚间复盘和单日收盘不足以安全覆盖全局姿态；本次只保留当期判断和authority=0先验。
  打法：no_change：环境、模式资格和有限容错已有纪律基础；执行能力分层先进入候选研究，不直接写入确定性playbook。
  待验证：复现XH-075并增加8月11日晚间来源绑定；新增‘模式按止损时延与盯盘能力分层’候选，全部authority=0。
  命中审计：完整逐字稿89170字节、30435字符，SHA-256为cd1889d8...d121；214个投资语义片段逐段覆盖；8月11日收盘广度、四个指数和八个来源点名案例已只读核对。
  工具缺口：前向记录环境与模式评分、可盯盘时段、触发到退出时延、三日持有边界、纪律违约、最大不利变动、含成本收益和组合回撤；禁止用盘后赢家回填。
- **2026-08-13 微信公众号复盘（2026-08-13_liu_shao_review.json）**
  启发：刘少狙击营在8月13日尾盘回落后仍把半导体视作A股主流核心，并以腾讯人工智能开支、美光向上突破和长鑫科技上市后约3.54万亿元市值作为理由；创新药只有上游服务表现，原研药尚缺新药上市催化，指数当月更适合横盘消化。文章最可复用的方法是建立投资错题本，按行业和时间回看过去判断，区分判断是否正确、原因是否成立以及实际资金是否执行，反复复习错误而不是只记住结果。
  姿态：不应用：刘少狙击营是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  打法：no_change：投资错题本与结果、过程分离只作为候选方法，未通过研究和人审门禁。
  待验证：no_change：本文强化2026-08-10已有的结果与过程分离原则，但没有提供足以新增或合并统计假设的独立样本。
  命中审计：完整公众号正文与一张信息型黄金历史截图已归档，证据绑定SHA-256 49530ce39dbd57bad4f2bc28331edc7baec8c8333a91acf7c3c9f6803507537d。
  工具缺口：no_issue_created：后续复盘可记录计划偏离、重复错误和纠正动作是否下降；未通过scripts/research_run.py与§10前不进入确定性策略。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-08-10 2026-08-10_xiaocao_morning.json: no_change：现行全局posture已过期，单场盘前材料与单日收盘核对不足以安全覆盖全局姿态；当前建议仅留在已发布决策审计。
  - 2026-08-10 2026-08-10_xiaocao_review.json: no_change：现行全局posture已过期，单场晚间复盘与单日收盘事实不足以安全覆盖全局姿态；只保留当期决策和authority=0先验。
  - 2026-08-11 2026-08-11_xiaocao_review.json: no_change：现行全局posture已过期39天，单场晚间复盘和单日收盘不足以安全覆盖全局姿态；本次只保留当期判断和authority=0先验。
  - 2026-08-13 2026-08-13_liu_shao_review.json: 不应用：刘少狙击营是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
- **Playbook/纪律**
  - 2026-08-10 2026-08-10_xiaocao_morning.json: no_change：轮动仓位、标的自身信号优先、广度不能单独开放追涨已在现有playbook和候选中表达。
  - 2026-08-10 2026-08-10_xiaocao_review.json: no_change：环境到分档仓位的链已由现有轮动纪律表达；一字板首断排除先进入候选研究，不直接写入确定性playbook。
  - 2026-08-11 2026-08-11_xiaocao_review.json: no_change：环境、模式资格和有限容错已有纪律基础；执行能力分层先进入候选研究，不直接写入确定性playbook。
  - 2026-08-13 2026-08-13_liu_shao_review.json: no_change：投资错题本与结果、过程分离只作为候选方法，未通过研究和人审门禁。
- **候选假设**
  - 2026-08-10 2026-08-10_xiaocao_morning.json: 复现XH-054、XH-059和XH-075，增加2026-08-10小草来源绑定；authority=0，不改确定性参数。
  - 2026-08-10 2026-08-10_xiaocao_review.json: 复现XH-075并增加8月10日晚间来源绑定；新增‘一字板前置首断可能弱于实体板’候选，全部authority=0。
  - 2026-08-11 2026-08-11_xiaocao_review.json: 复现XH-075并增加8月11日晚间来源绑定；新增‘模式按止损时延与盯盘能力分层’候选，全部authority=0。
  - 2026-08-13 2026-08-13_liu_shao_review.json: no_change：本文强化2026-08-10已有的结果与过程分离原则，但没有提供足以新增或合并统计假设的独立样本。
- **命中审计**
  - 2026-08-10 2026-08-10_xiaocao_morning.json: 完整逐字稿2695字符、22段，开中尾审计通过；8月10日收盘上涨3968家、下跌1391家，上证与创业板/科创50方向分化。
  - 2026-08-10 2026-08-10_xiaocao_review.json: 完整逐字稿8310字符、127行，SHA-256为7b6469d1...c5e3；64个投资语义片段逐段覆盖；8月10日收盘指数、AI硬件核心和高标案例已核对，本地推荐与Book记录分账。
  - 2026-08-11 2026-08-11_xiaocao_review.json: 完整逐字稿89170字节、30435字符，SHA-256为cd1889d8...d121；214个投资语义片段逐段覆盖；8月11日收盘广度、四个指数和八个来源点名案例已只读核对。
  - 2026-08-13 2026-08-13_liu_shao_review.json: 完整公众号正文与一张信息型黄金历史截图已归档，证据绑定SHA-256 49530ce39dbd57bad4f2bc28331edc7baec8c8333a91acf7c3c9f6803507537d。
- **工具/流程提案**
  - 2026-08-10 2026-08-10_xiaocao_morning.json: 继续前向记录跷跷板日标的自身信号、广度与主线集中度、分档仓位路径；禁止用收盘赢家回填盘前命中。
  - 2026-08-10 2026-08-10_xiaocao_review.json: 前向记录午后修复幅度与次日低吸赔率、轮动仓位档位、首断前一涨停形态、实际可成交性和左尾；禁止用盘后赢家回填盘前命中。
  - 2026-08-11 2026-08-11_xiaocao_review.json: 前向记录环境与模式评分、可盯盘时段、触发到退出时延、三日持有边界、纪律违约、最大不利变动、含成本收益和组合回撤；禁止用盘后赢家回填。
  - 2026-08-13 2026-08-13_liu_shao_review.json: no_issue_created：后续复盘可记录计划偏离、重复错误和纠正动作是否下降；未通过scripts/research_run.py与§10前不进入确定性策略。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：1
- 自动落地候选数量：0

## 验证
- bash scripts/auto_daily.sh weekly: PASS (terminal weekly plan ready; run once)
- jq weekly plan route/structure check: PASS (1 proposal; 8 unmapped candidates preserved)
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src .venv/bin/python scripts/strategy_protocols.py --check: PASS (2 protocols)
- PYTHONPATH=src .venv/bin/python -m pytest tests/test_weekly_deep_review.py -q: PASS (14 passed)
- git diff --check: PASS

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 91 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-08-14/instrumentation-mapping-2026-08-08-2026-08-14.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 65,
    "candidate_assertions": 153,
    "candidate_to_tested": 0.11,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 91,
    "candidates_untested": 81,
    "dedup_ratio": 0.59,
    "instrumentation_todos": 34,
    "median_recurrence": 1,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 582,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 65
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 2,
  "pre_existing_dirty_sample": [
    " M kronos_screen/HYPOTHESES.jsonl",
    "?? .scratch/kol-writer-self-repair/"
  ]
}
```
