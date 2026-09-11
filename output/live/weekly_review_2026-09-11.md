# 小草每周深度复盘 2026-09-11

## 先看结论

- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：3 个；另有 1 条本地工作区提醒，见下一节。
- 整体框架复盘（有证据引用的分析，非收益认证）：保留现行有界 KOL 的来源复核、当前适用性、独立审核、合法发布与下一合法消费边界，但把其盈利或尾部保护增量明确标为未证实并优先补齐反事实和时钟。18 个发布包中 17 个中性，唯一 buy_scale=0 的暂停新增风险到 9 月 11 日 14:21 才发布，不能追认上午纸盘开仓或 13:55 检查点；当前证据既不能把本周亏损归因于 KOL，也不能把少用资金当作信息优势。1/4/12 周实际复用 9 月 7—11 日的近期观测，没有同 freeze、同资本、费后可成交的 no-KOL/current/challenger 配对；live 与 paper 必须分账，paper 最后有效 NAV 124137.62 之后的 15:15 最新风险回执为陈旧估值导致 BLOCKED，不能冒充终态 NORMAL。框架应 refine 取证与时效，challenger 只能进入 authority=0 隔离研究；不改正式 freeze、策略、资本、安全或实盘权限。
- 结论证据：`output/live/kol_policy/context/92d608d546c6cbc900ddb53343ebdef4029ddb1e2996d67c200ffc689ddc18d6.context.json`（sha256=a4c4bd3a1dc94166a2b4cb1a27b82a5bd271ba8e80f44721c2123ffd79c2ecaa）；`output/live/kol_policy/decisions/kol-b-sparse-20260911-1355-pause-adds-6478a1ac-v1.json`（sha256=fee08a26a39ba69b90d4b7c14e9242c622b87466f87e0a32743f3f8949c10459）；`output/live/kol_policy/source_verifications/kol-b-sparse-20260911-1355-pause-adds-6478a1ac-v1.json`（sha256=eb0310fe879c5b50a1c8db6349ee8e6817c2b8105cc9fed0d2c9937f52ead866）；`output/live/kol_policy/account_risk/live_B.jsonl`（sha256=eaa06f929601663d5a2f224622514963c81c138c80f038e5b7696439c11d210c）；`output/live/kol_policy/account_risk/risk_receipts/5930e8979e44932c47e4d24e5f72dd66df656687d483212ed4ec23d3cf60030d.json`（sha256=0e10c97c06b7127be39ecad000f61ad392dd0f8b31dae92adee0f26412918b18）；`output/live/book_b_live_execution/book_b_live_decisions.jsonl`（sha256=6f439e34b6d8401ac3ce8d09d5b6950f4f66b6a8b9ac3d4a6d2023bd85cdcbc2）；`output/live/book_b_live_execution/runs/2026-09-11.json`（sha256=7c7801e9aa0ec2d2346d0e89b60f78fe744156166acdd17823be085c5faa5b98）
- 待核证据：1/4/12 周缺同一冻结、同一资本与费用口径的 no-KOL/current/challenger 可成交配对；现有三个窗口复用同一段近期 NAV 观察，不能形成独立跨窗结论。；缺 source occurrence→received→request→模型开始/完成→review→publish→next legal consume→intent→成交/费用的全链时钟，不能把 review_latency 当端到端延迟。；paper 的 5 组 10 个 consumption/结果文件被固定 inventory 判为 missing_or_invalid_evidence，live/paper consumption 日志缺失；消费计数不是成交或收益证据。；registry_only 不等于远端来源完整；历史正文未全加载、同一市场快照被多篇复用、发生日与上传时间混杂，不能按作者多数投票或把重收当新信号。；缺上游请求/数据时间、版本 hash、全量行数、拒绝原因与 readiness 到 freeze 的链；COLD/无 ★E 不证明候选全集完整，单个赢家也不证明过度过滤。；缺逐账户资金流、完整结算、费滑、现金时间积分、错失上涨与避免下跌的成对证据；paper 最新 BLOCKED 也不能被上一条 NORMAL 覆盖。；prior_experiment_follow_up 没有历史槽位；未记录不等于完成、失败或回滚，本周三个槽位都是未启动的新提案。
- 比较框架：无 KOL 基线 / 现行有界 KOL / 挑战者；分别检查入口过滤、模式和资金利用率。
- 纸实逐账户分开；1/4/12 周重叠窗口不是独立样本。小样本不宣称因果胜率或稳定收益，不自动推广实盘。

## 需要你看/确认的事项

- **需要确认** `kol-baseline-paired-counterfactual-2026-09-11`：建立无 KOL 配对基线
- **需要确认** `kol-legal-consume-timeline-2026-09-11`：补齐 KOL 时钟与成交链
- **需要确认** `kol-authority-zero-candidate-challenger-2026-09-11`：隔离检验上游候选挑战者
- **本地工作区提醒，不是策略判断**：有 7 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：kronos_screen/HYPOTHESES.jsonl, reference/experience/distill_action_log.jsonl, reference/experience/distilled/2026-09-03_a_alex_review.json, reference/experience/distilled/2026-09-03_liu_shao_review.json, reference/experience/distilled/2026-09-04_lv_xiaotong_review.json；另有 2 个。

## 这批转录给我的启发
- **2026-09-06 资料复核（2026-09-06_lv_collection_ai_framework_review.json）**
  启发：从AI产业摘要中保留应用护城河、用量与利润拆分、机器人验证条件三条候选方法；明确摘要事实误差和未署名边界。
  姿态：not_applied:other_author
  待验证：no_change:保留方法，不新增未定义样本的重复假说
  命中审计：完整3页及123段复读；事实与来源分开。

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-09-06 2026-09-06_lv_collection_ai_framework_review.json: not_applied:other_author
- **候选假设**
  - 2026-09-06 2026-09-06_lv_collection_ai_framework_review.json: no_change:保留方法，不新增未定义样本的重复假说
- **命中审计**
  - 2026-09-06 2026-09-06_lv_collection_ai_framework_review.json: 完整3页及123段复读；事实与来源分开。

## 上期试验与失败跟进（先于新增试验，未记录不等于完成）

- 缺少可读的上期结构化试验记录；不能据此宣称全部完成。

## 整体框架试验槽位（待取证与设计，不是合格变更候选）

- 目标：验证本周及后续经济结果主要由既有 ★E、模式、资金与执行门解释，还是 KOL 确有超出少用资金的增量；建立可复放、同信息集、同风险暴露的 no-KOL/current 配对账。
  - 证伪条件：在完整逐笔合法成交与成本、同风险预算、跨窗口/OOS、剔除最大赢家并按来源聚类后，有界 KOL 仍显示不能由资格、执行或少用资金解释的稳定尾部或净收益改善，则推翻‘无增量’解释；证据不全保持不确定，不计 PASS。
  - 必要证据：按 live/paper 分别补齐 intent/claim、legal consume、broker/paper result、T+1/行情/拒绝理由、费用、资金流与每日结算 NAV；每个不可变 freeze 重建同整手、资金与退出的 baseline，并按 decision sha 与真实生效事件连接覆盖，过期或迟到不回填；逐笔报告净收益、尾部、回撤、平均与峰值暴露、现金时间积分、费用、避免下跌和错失上涨，按模式/日期/来源聚类；预注册等风险对照、OOS、多重比较及最低有效样本；当前只有一周标记样本时不得宣称 4/12 周验证
  - 回滚：本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。
  - 本次跟进（报告声明）：待复核，尚无完成证明
  - 负责人：xiaocao weekly review maintainer（隔离研究执行须另经研究门授权）；下次复核：2026-09-18。
- 目标：检验现行有界 KOL 是否以更少尾部损失补偿等待、过期、语义歧义与错失机会；重点检验来源条件能否在第一次合法开仓前完成核实，而不是增加 post-morning 中性包数量。
  - 证伪条件：点时合法的配对反事实显示错失上涨、费用和执行漏损抵消尾部收益，或改善只由一周、一个来源或一个赢家解释；若及时化只增加发布数量而不提高合法消费覆盖，也不支持改善命题。
  - 必要证据：统一记录 source occurrence/发布时间、received、request、模型开始/完成、review、published、valid_until 与 next legal consume；对 9 月 7 日窗口误判、9 月 11 日 post-morning 与 14:21 pause 做不可回放时间线审计，分开迟延、语义不可执行和确定性执行门；预先列出 exact source mode、trigger/falsifier 与 production 模式映射，保留连板评分未重估反证，不发明阈值或牺牲独立审核换速度；每次 pause 标记当时是否真有合法新增机会及重叠 T+1/未成交限制，衡量净增量而非 no-action 率
  - 回滚：本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。
  - 本次跟进（报告声明）：待复核，尚无完成证明
  - 负责人：xiaocao weekly review maintainer（时钟与 lineage 实现须另行确认负责人）；下次复核：2026-09-18。
- 目标：检验上游入口或模式集合是否造成局部最优：预登记竞价与盘中模式语义及点时完整机会集，在 authority=0 隔离队列观察正式 freeze 外候选，再比较 no-KOL/current/challenger。
  - 证伪条件：在同本金、同整手/费用、同合法时点及流动性/T+1/退出约束、OOS 和完整失败样本下，挑战者未同时改善机会覆盖与风险调整表现，或优势依赖事后补榜、BJSE、模糊名字、单日赢家或不可复现评分版本，则拒绝；数据不足不作 PASS。
  - 必要证据：每来源与模式的请求/数据时间、版本 hash、完整行数、拒绝计数、readiness 与首次出现时间；预注册竞价、固定 9:31 与盘中候选研究层，不细扫最佳秒点或事后分数阈值，并锁定模式持有/退出和宽邻域稳健性；比较正式入口排除候选，分开 COLD 双 alpha 反证、真正未覆盖入口、身份/交易所/成交性硬拒绝；不改生产 freeze 或新增 live 候选；若讨论 v2，仍限小草本人、同日 freeze 内精确 mode-follow、COLD 非 UNKNOWN、非 BJSE、最多三槽且同模式一只
  - 回滚：本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。
  - 本次跟进（报告声明）：待复核，尚无完成证明
  - 负责人：xiaocao weekly review maintainer（候选完整性研究须另经研究门授权）；下次复核：2026-09-18。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- KOL 固定复盘输入（仅观察，不增加自动落地权限）：output/live/kol_policy/context/*.context.json, output/live/kol_policy/decisions/*.json, output/live/book_b_live_execution/consumption.jsonl, output/live/book_b_live_execution/book_b_live_decisions.jsonl, output/live/book_b_live_execution/runs/*.json, output/live/kol_policy/account_risk/live_B.jsonl, output/live/paper_decision_support/consumption/*.json, output/live/paper_decision_support/consumption.jsonl, output/live/kol_policy/account_risk/risk_receipts/*.json, output/live/flywheel_change_ledger.jsonl, output/live/kol_policy/requests/*.json, output/live/kol_policy/source_verifications/*.json
- 提案数量：3
- 自动落地候选数量：0

## 验证
- bash scripts/auto_daily.sh weekly: PASS (terminal weekly plan ready; run exactly once)
- weekly routed plan structure: PASS (3 proposals; 0 auto-apply candidates; 3 unstarted KOL experiment slots)
- Astra evidence review: PASS (358 unique inventory files hash-matched; 25 fixed refs; 3 slots)
- independent parent review: PASS (25 refs in fixed inventory; 18 decisions = 17 neutral + 1 pause; paper terminal BLOCKED separated)
- PYTHONPATH=src .venv/bin/python scripts/data_doctor.py: PASS (no dirty-data findings)
- PYTHONPATH=src .venv/bin/python scripts/status.py --json: PASS (A/B/T authoritative readback; market_date=2026-09-11)
- bash -n scripts/auto_daily.sh: PASS
- PYTHONPATH=src .venv/bin/python scripts/strategy_protocols.py --check: PASS (3 protocols)
- PYTHONPATH=src .venv/bin/python -m pytest tests/test_weekly_deep_review.py -q: PASS (14 passed)
- git diff --check: PASS

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 139 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-09-11/kol-baseline-paired-counterfactual-2026-09-11.md
- .scratch/weekly-deep-review/2026-09-11/kol-legal-consume-timeline-2026-09-11.md
- .scratch/weekly-deep-review/2026-09-11/kol-authority-zero-candidate-challenger-2026-09-11.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 84,
    "candidate_assertions": 205,
    "candidate_to_tested": 0.07,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 139,
    "candidates_untested": 129,
    "dedup_ratio": 0.68,
    "instrumentation_todos": 52,
    "median_recurrence": 1,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 610,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 84
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 97,
  "pre_existing_dirty_sample": [
    " M kronos_screen/HYPOTHESES.jsonl",
    " M reference/experience/distill_action_log.jsonl",
    " M reference/experience/xiaocao_hypotheses.jsonl",
    " M tests/test_kol_lv_subscription.py",
    "?? .scratch/book-b-live-repair-2026-09-04-closing/",
    "?? .scratch/kol-alert-reminder-correction-20260908/",
    "?? .scratch/kol-astra-routing-2026-09-06/",
    "?? .scratch/kol-writer-self-repair/",
    "?? output/live/book_b_live_allocation_facts_2026-08-23.json",
    "?? output/live/book_b_live_allocation_facts_2026-08-24.json",
    "?? output/live/book_b_live_allocation_facts_2026-08-25.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-01.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-02.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-04.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-07.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-08.json",
    "?? output/live/book_b_live_allocation_facts_2026-09-11.json",
    "?? output/live/book_b_live_execution/",
    "?? output/live/book_b_live_freeze_2026-08-24.jsonl",
    "?? output/live/book_b_live_freeze_2026-08-25.jsonl"
  ],
  "kol_system_review_status": "pending_analysis",
  "kol_inventory_sha256": "5d7e7b04f669a9b0f079a2da60f04decd4e028a57ff9fccbdbf1aa9c1add8cb0",
  "kol_audit_feedback": {
    "consumption": {
      "live": {
        "book_counts": {
          "B": 32
        },
        "consumption_container_count": 27,
        "decision_counts": {
          "kol-b-precheck-20260908-1428-astra-neutral-v1": 3,
          "kol-b-sparse-20260907-1355-astra-neutral-v1": 2,
          "kol-b-sparse-20260907-1430-astra-neutral-v1": 6,
          "kol-b-sparse-20260908-0950-astra-neutral-v1": 2,
          "kol-b-sparse-20260908-1050-astra-neutral-v1": 1,
          "kol-b-sparse-20260908-1325-astra-neutral-v1": 1,
          "kol-b-sparse-20260909-1025-astra-neutral-8c835b5a-v1r1": 1,
          "kol-b-sparse-20260909-1325-astra-neutral-38a3f375-v1": 4,
          "kol-b-sparse-20260910-1055-astra-neutral-12b5dc0e-v1": 3,
          "kol-xiaocao-sunday-pilot-20260906-reviewed-v2": 9
        },
        "evidence_sha256": "f85e9a0cd1f06bb4c224d572d74a44dd801bb612b779ca03abd53c25773f2cc3",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 22,
        "legacy_file_count": 11,
        "missing_consumption_clock_count": 10,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 0,
        "paper_terminal_status_counts": {},
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 22,
        "record_count": 32,
        "reported_execution_status_counts": {},
        "skip_record_count": 0,
        "source_file_count": 17,
        "status": "read",
        "unbound_decision_reference_count": 28
      },
      "paper": {
        "book_counts": {
          "B": 5
        },
        "consumption_container_count": 5,
        "decision_counts": {
          "kol-b-precheck-20260908-1428-astra-neutral-v1": 1,
          "kol-b-sparse-20260907-1430-astra-neutral-v1": 1,
          "kol-b-sparse-20260909-1325-astra-neutral-38a3f375-v1": 1,
          "kol-b-sparse-20260910-1055-astra-neutral-12b5dc0e-v1": 1,
          "kol-xiaocao-sunday-pilot-20260906-reviewed-v2": 1
        },
        "evidence_sha256": "49cfbdeb464b0a64a4f76e3e14655f393eae64b7abed1cf63f08572bb99bd18c",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 5,
        "legacy_file_count": 0,
        "missing_consumption_clock_count": 5,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 3,
        "paper_terminal_status_counts": {
          "bought": 3,
          "no_buy": 2
        },
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 5,
        "record_count": 5,
        "reported_execution_status_counts": {},
        "skip_record_count": 2,
        "source_file_count": 10,
        "status": "read",
        "unbound_decision_reference_count": 5
      }
    },
    "execution_verification": "not_performed",
    "profit_attribution": "not_established",
    "published_decision_count": 18,
    "status": "audited"
  },
  "kol_audit_snapshot_binding": {
    "live": "matched",
    "paper": "matched"
  },
  "kol_experiment_slots": [
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-baseline_no_kol",
      "falsifier": "在完整逐笔合法成交与成本、同风险预算、跨窗口/OOS、剔除最大赢家并按来源聚类后，有界 KOL 仍显示不能由资格、执行或少用资金解释的稳定尾部或净收益改善，则推翻‘无增量’解释；证据不全保持不确定，不计 PASS。",
      "follow_up": {
        "conclusion": null,
        "disposition": null,
        "evidence_refs": [],
        "status": "pending_not_started"
      },
      "id": "baseline_no_kol",
      "next_review": "2026-09-18",
      "objective": "验证本周及后续经济结果主要由既有 ★E、模式、资金与执行门解释，还是 KOL 确有超出少用资金的增量；建立可复放、同信息集、同风险暴露的 no-KOL/current 配对账。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（隔离研究执行须另经研究门授权）",
      "required_evidence": [
        "按 live/paper 分别补齐 intent/claim、legal consume、broker/paper result、T+1/行情/拒绝理由、费用、资金流与每日结算 NAV",
        "每个不可变 freeze 重建同整手、资金与退出的 baseline，并按 decision sha 与真实生效事件连接覆盖，过期或迟到不回填",
        "逐笔报告净收益、尾部、回撤、平均与峰值暴露、现金时间积分、费用、避免下跌和错失上涨，按模式/日期/来源聚类",
        "预注册等风险对照、OOS、多重比较及最低有效样本；当前只有一周标记样本时不得宣称 4/12 周验证"
      ],
      "rollback": "本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。",
      "status": "needs_evidence_and_design"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-current_bounded",
      "falsifier": "点时合法的配对反事实显示错失上涨、费用和执行漏损抵消尾部收益，或改善只由一周、一个来源或一个赢家解释；若及时化只增加发布数量而不提高合法消费覆盖，也不支持改善命题。",
      "follow_up": {
        "conclusion": null,
        "disposition": null,
        "evidence_refs": [],
        "status": "pending_not_started"
      },
      "id": "current_bounded",
      "next_review": "2026-09-18",
      "objective": "检验现行有界 KOL 是否以更少尾部损失补偿等待、过期、语义歧义与错失机会；重点检验来源条件能否在第一次合法开仓前完成核实，而不是增加 post-morning 中性包数量。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（时钟与 lineage 实现须另行确认负责人）",
      "required_evidence": [
        "统一记录 source occurrence/发布时间、received、request、模型开始/完成、review、published、valid_until 与 next legal consume",
        "对 9 月 7 日窗口误判、9 月 11 日 post-morning 与 14:21 pause 做不可回放时间线审计，分开迟延、语义不可执行和确定性执行门",
        "预先列出 exact source mode、trigger/falsifier 与 production 模式映射，保留连板评分未重估反证，不发明阈值或牺牲独立审核换速度",
        "每次 pause 标记当时是否真有合法新增机会及重叠 T+1/未成交限制，衡量净增量而非 no-action 率"
      ],
      "rollback": "本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。",
      "status": "needs_evidence_and_design"
    },
    {
      "authority": "proposal_or_existing_research_gate",
      "auto_apply_eligible": false,
      "experiment_id": "weekly-2026-09-11-kol_challenger",
      "falsifier": "在同本金、同整手/费用、同合法时点及流动性/T+1/退出约束、OOS 和完整失败样本下，挑战者未同时改善机会覆盖与风险调整表现，或优势依赖事后补榜、BJSE、模糊名字、单日赢家或不可复现评分版本，则拒绝；数据不足不作 PASS。",
      "follow_up": {
        "conclusion": null,
        "disposition": null,
        "evidence_refs": [],
        "status": "pending_not_started"
      },
      "id": "kol_challenger",
      "next_review": "2026-09-18",
      "objective": "检验上游入口或模式集合是否造成局部最优：预登记竞价与盘中模式语义及点时完整机会集，在 authority=0 隔离队列观察正式 freeze 外候选，再比较 no-KOL/current/challenger。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（候选完整性研究须另经研究门授权）",
      "required_evidence": [
        "每来源与模式的请求/数据时间、版本 hash、完整行数、拒绝计数、readiness 与首次出现时间",
        "预注册竞价、固定 9:31 与盘中候选研究层，不细扫最佳秒点或事后分数阈值，并锁定模式持有/退出和宽邻域稳健性",
        "比较正式入口排除候选，分开 COLD 双 alpha 反证、真正未覆盖入口、身份/交易所/成交性硬拒绝",
        "不改生产 freeze 或新增 live 候选；若讨论 v2，仍限小草本人、同日 freeze 内精确 mode-follow、COLD 非 UNKNOWN、非 BJSE、最多三槽且同模式一只"
      ],
      "rollback": "本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。",
      "status": "needs_evidence_and_design"
    }
  ]
}
```
