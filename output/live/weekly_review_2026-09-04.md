# 小草每周深度复盘 2026-09-04

## 先看结论
- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：5 个；另有 1 条本地工作区提醒，见下一节。

## 需要你看/确认的事项
- **需要确认** `housing-macro-transmission-contract-2026-09-04`：定义住房与宏观科技传导合同
- **需要确认** `company-technology-governance-panel-contract-2026-09-04`：定义公司技术与治理事实面板
- **需要确认** `breadth-sector-persistence-contract-2026-09-04`：定义市场广度与板块持续性合同
- **需要确认** `risk-budget-volatility-boundary-contract-2026-09-04`：定义风险预算与波动边界合同
- **需要确认** `primary-market-exit-contract-2026-09-04`：定义一级项目估值退出合同
- **本地工作区提醒，不是策略判断**：有 7 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl, reference/experience/distill_action_log.jsonl, reference/experience/distilled/2026-09-03_a_alex_review.json, reference/experience/distilled/2026-09-03_liu_shao_review.json, reference/experience/distilled/2026-09-04_lv_xiaotong_review.json；另有 2 个。

## 这批转录给我的启发
- **2026-09-02 review（2026-09-02_a_alex_review.json）**
  启发：作者认为科技成长长期弹性高但回撤深，当前基本面线索偏强却仍受高利率和政策风险压制；可复用的核心方法是按可承受最大损失定仓位、等待高波动主题回撤后再核验基本面，并用分散配置降低轮动冲击。
  姿态：not_applied_other_author
  待验证：two_new_candidates
  命中审计：bound_to_complete_official_article_markdown_sha256
  工具缺口：research_loss_budget_and_drawdown_entry_rules
- **2026-09-03 review（2026-09-03_a_alex_review.json）**
  启发：作者把9月3日的盘面解释为低成交环境下红利与科技的阶段性资金轮动，并同时提示AI产业高景气与模型降价压利润的两面性；可复用的判断是把轮动、增量资金、订单兑现、毛利率和家庭风险预算分层核验，不把单日反弹或单条产业新闻升级为组合方向。
  姿态：not_applied_other_author
  待验证：no_new_candidates_reinforces_XH-118_XH-122_XH-128
  命中审计：complete_official_article_and_image_notes_bound_to_sha256
  工具缺口：track_rotation_breadth_volume_orders_margin_cashflow
- **2026-09-03 review（2026-09-03_liu_shao_review.json）**
  启发：作者把当日市场概括为缩量、指数稳定但内部分化极端，给银行、资源、半导体、创新药、消费和机器人分别设定观察定位，并用‘业绩是分子、利率是分母’解释估值敏感性；可复用的判断是先识别市场是否缺少可验证的方向，再用利率、盈利、广度和行业持续性决定是否等待，不把板块标签直接变成交易。
  姿态：not_applied_other_author
  待验证：no_new_candidates_reinforces_XH-118_XH-122
  命中审计：complete_official_article_and_decorative_image_bound_to_sha256
  工具缺口：track_breadth_volume_rates_sector_persistence
- **2026-09-04 盘后直播（2026-09-04_lv_xiaotong_review.json）**
  启发：吕晓彤围绕一级市场估值、机器人与AI兑现、公司融资治理、全球科技难度和家庭资产配置给出多层判断；最可复用的是把叙事拆成主体、估值、订单、现金流、退出和失效条件，模糊对象停在核验边界。
  姿态：不应用：吕晓彤是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
  打法：no_deterministic_change：补充一级市场退出核验、技术主题中间变量、融资治理条款和家庭风险预算候选。
  待验证：新增五条authority=0候选：一级市场研究边界、技术主题验证、AI需求分层、公司治理证据和家庭复杂工具风险；必须通过research_run.py与§10人审。
  命中审计：完整视频逐字稿304个稳定分段已逐段审阅；证据SHA-256为847d099134f18407076a124f26e76ef9831b006554565b1c42c07df107c44e98；当前市场事实单独写入语义输入。
  工具缺口：建立一级项目退出、技术主题中间变量、融资治理条款、海外产品条款和家庭风险预算的可复核面板；不改动确定性策略。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-09-02 2026-09-02_a_alex_review.json: not_applied_other_author
  - 2026-09-03 2026-09-03_a_alex_review.json: not_applied_other_author
  - 2026-09-03 2026-09-03_liu_shao_review.json: not_applied_other_author
  - 2026-09-04 2026-09-04_lv_xiaotong_review.json: 不应用：吕晓彤是其他作者，本条只写authority=0知识，不修改小草posture_current或REGIME_TIMELINE。
- **Playbook/纪律**
  - 2026-09-04 2026-09-04_lv_xiaotong_review.json: no_deterministic_change：补充一级市场退出核验、技术主题中间变量、融资治理条款和家庭风险预算候选。
- **候选假设**
  - 2026-09-02 2026-09-02_a_alex_review.json: two_new_candidates
  - 2026-09-03 2026-09-03_a_alex_review.json: no_new_candidates_reinforces_XH-118_XH-122_XH-128
  - 2026-09-03 2026-09-03_liu_shao_review.json: no_new_candidates_reinforces_XH-118_XH-122
  - 2026-09-04 2026-09-04_lv_xiaotong_review.json: 新增五条authority=0候选：一级市场研究边界、技术主题验证、AI需求分层、公司治理证据和家庭复杂工具风险；必须通过research_run.py与§10人审。
- **命中审计**
  - 2026-09-02 2026-09-02_a_alex_review.json: bound_to_complete_official_article_markdown_sha256
  - 2026-09-03 2026-09-03_a_alex_review.json: complete_official_article_and_image_notes_bound_to_sha256
  - 2026-09-03 2026-09-03_liu_shao_review.json: complete_official_article_and_decorative_image_bound_to_sha256
  - 2026-09-04 2026-09-04_lv_xiaotong_review.json: 完整视频逐字稿304个稳定分段已逐段审阅；证据SHA-256为847d099134f18407076a124f26e76ef9831b006554565b1c42c07df107c44e98；当前市场事实单独写入语义输入。
- **工具/流程提案**
  - 2026-09-02 2026-09-02_a_alex_review.json: research_loss_budget_and_drawdown_entry_rules
  - 2026-09-03 2026-09-03_a_alex_review.json: track_rotation_breadth_volume_orders_margin_cashflow
  - 2026-09-03 2026-09-03_liu_shao_review.json: track_breadth_volume_rates_sector_persistence
  - 2026-09-04 2026-09-04_lv_xiaotong_review.json: 建立一级项目退出、技术主题中间变量、融资治理条款、海外产品条款和家庭风险预算的可复核面板；不改动确定性策略。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- 提案数量：5
- 自动落地候选数量：0

## 验证
- bash scripts/auto_daily.sh weekly: PASS (terminal weekly plan ready; run exactly once)
- weekly routed plan structure: PASS (5 proposals; 0 auto-apply candidates)
- PYTHONPATH=src .venv/bin/python scripts/data_doctor.py: PASS (no dirty-data findings)
- PYTHONPATH=src .venv/bin/python scripts/status.py --json: PASS (A/B/T authoritative readback; market_date=2026-09-04)
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src .venv/bin/python scripts/strategy_protocols.py --check: PASS (3 protocols)
- PYTHONPATH=src .venv/bin/python -m pytest tests/test_weekly_deep_review.py -q: PASS (14 passed)
- git diff --check: PASS

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 130 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-09-04/housing-macro-transmission-contract-2026-09-04.md
- .scratch/weekly-deep-review/2026-09-04/company-technology-governance-panel-contract-2026-09-04.md
- .scratch/weekly-deep-review/2026-09-04/breadth-sector-persistence-contract-2026-09-04.md
- .scratch/weekly-deep-review/2026-09-04/risk-budget-volatility-boundary-contract-2026-09-04.md
- .scratch/weekly-deep-review/2026-09-04/primary-market-exit-contract-2026-09-04.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 80,
    "candidate_assertions": 195,
    "candidate_to_tested": 0.08,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 130,
    "candidates_untested": 120,
    "dedup_ratio": 0.67,
    "instrumentation_todos": 49,
    "median_recurrence": 1.0,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 603,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 80
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 63,
  "pre_existing_dirty_sample": [
    " M kronos_screen/HYPOTHESES.jsonl",
    " M reference/experience/distill_action_log.jsonl",
    " M reference/experience/xiaocao_hypotheses.jsonl",
    " M tests/test_kol_lv_subscription.py",
    "?? .scratch/book-b-live-repair-2026-09-04-closing/",
    "?? .scratch/kol-writer-self-repair/",
    "?? output/live/book_b_live_allocation_facts_2026-08-23.json",
    "?? output/live/book_b_live_allocation_facts_2026-08-24.json",
    "?? output/live/book_b_live_allocation_facts_2026-08-25.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-01.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-02.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-04.json",
    "?? output/live/book_b_live_execution/",
    "?? output/live/book_b_live_freeze_2026-08-24.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-25.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-26.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-27.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-28.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-31.jsonl",
    "?? output/live/book_b_live_freeze_2026-09-01.jsonl"
  ]
}
```
