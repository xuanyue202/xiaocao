# 小草每周深度复盘 2026-09-18

## 先看结论

- 本周模式：只给提案，等你确认（`PROPOSAL_ONLY`）。
- 自动改策略代码：没有。没有完整证据链时只产出提案/审计，不想当然改策略。
- 需要你确认的事项：1 个；另有 1 条本地工作区提醒，见下一节。
- 整体框架复盘（有证据引用的分析，非收益认证）：保留来源核验、独立 review、有效期、冻结候选、既有资本和 durable-intent 边界，并把验证单位细化为‘点时来源条件—合法消费—实际增量效果’。本周 19 个发布判断为 12 个中性、7 个暂停，全部为 v1；1/4/12 周窗口高度重叠，收益、回撤、错失上涨和执行损失均无同冻结配对反事实。现有证据既不能证明 KOL 改善收益，也不能证明原入口过度过滤造成可实现损失；三个上期实验均未运行，继续以 no-KOL、现行有界层和 authority=0 challenger 三框架取证，不新开槽、不自动推广。
- 结论证据：`output/live/flywheel_change_ledger.jsonl`（sha256=eb3e616985491b7925af6312a091130a74124cabb1c74636ba318297c6449445）；`output/live/book_b_live_execution/book_b_live_decisions.jsonl`（sha256=e8a6c26e7f6726408d98541fde3d438c2a6c8c83681715ebb41549b45c8d2018）；`output/live/book_b_live_execution/runs/2026-09-17.json`（sha256=e09c1c65486cbb07457c16de481a7cdc70cd46bb34ebc5c1ae5d31340e8e184c）；`output/live/kol_policy/account_risk/live_B.jsonl`（sha256=7ad378bfb4ecc271b16246a7f4954decfd2768b7d37610072e4f87ad6144b1cf）；`output/live/kol_policy/account_risk/risk_receipts/c5a97e94f706e7e8466f3f1ce5d9650269fa4fc6f0ea692c441d54123ef22977.json`（sha256=57fec2ebf79304aab66603e0443c2d4878bb6498813828bc9fc3944e54792b9b）；`output/live/kol_policy/decisions/kol-b-live-opening-20260916-pause-adds-329fb25c-v1.json`（sha256=88f4078d1d712a69a8ba52d8c0cf3ff89d66bd29bb85bdb12364a244e58799e5）；`output/live/kol_policy/decisions/kol-b-paper-20260916-morning-pause-astra-v1.json`（sha256=0b1552c2b5b3ed1fb98b77b25f89efa6d8298abcbf9730752f47b95209323d13）；`output/live/kol_policy/decisions/kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1.json`（sha256=31402b91fc41850b048f6ca9956943455c753347c3307e1af458576604aad295）；`output/live/kol_policy/decisions/kol-b-paper-sparse-20260918-1325-neutral-3ae43f5a-v1.json`（sha256=3e58c935ca8fd993f420b84dd865c7202cac013bd3dc5b7e2d02b8830f9ac2ce）
- 待核证据：逐账户、同 freeze、同资本/整手/退出及费后的 no-KOL/current/challenger 配对反事实；完整每日结算 NAV、暴露、现金时间积分、费用、错失上涨、避免下跌与执行损失；4/12 周当前与 1 周高度重叠；live/paper canonical consumption 日志缺失；18 个 paper consumption 文件被固定 inventory 标为 missing_or_invalid_evidence；source occurrence 到下一合法消费、intent、fill/fee、结算的统一时钟；过期引用不能计作有效覆盖；完整候选/拒绝面板、first-seen、模式映射、可成交价格、共同退出、OOS 与失败样本；上期三个实验的实际运行输出、反证、成本及回滚证据；有效 v2 mode-follow 与实际应用证据；当前固定 37 个判断均为 v1，mode override、skip、discretionary exit 均为零
- 比较框架：无 KOL 基线 / 现行有界 KOL / 挑战者；分别检查入口过滤、模式和资金利用率。
- 纸实逐账户分开；1/4/12 周重叠窗口不是独立样本。小样本不宣称因果胜率或稳定收益，不自动推广实盘。
- 旧试验跟进：3 项需先复核（历史状态仅为报告声明），再决定本周最多三个槽位；不自动启动。

## 需要你看/确认的事项

- **补流程工具**：工具缺口真实存在，但缺少点时来源/provenance、字段及缺失值契约、明确消费方、验收夹具和基线量化；本周不能 AUTO_APPLIED。 这是只读观测工具，不改策略/参数/成交/账户；以后这类固定输入里的工具缺口默认直接优化。
- **本地工作区提醒，不是策略判断**：有 2 个本来就 dirty 的可改路径，本周自动化不会碰它们。样例：src/xiaocao/live/app_test_window.py, tests/test_app_preopen_grant.py。

## 这批转录给我的启发
- **2026-09-15 微信公众号市场与方法蒸馏（2026-09-15_a_alex_review.json）**
  启发：文章把高利率、A股资金缓慢净流出和宏观K型分化连成一个结构行情框架：高利率压制总量估值，融资与减持造成的缓慢失血压制全面指数行情，但资金集中流向硬科技、外需和新质生产力时仍可出现结构机会。可复用之处是把总量流动性、行业资金集中度和产业基本面分层验证；它不构成自动加仓、选股或参数调整规则。
  姿态：not_applied_other_author
  待验证：no_new_candidates_reinforces_XH-064_XH-118
  命中审计：user_transferred_wechat_comment_ocr_bound_to_official_handoff_and_sha256
  工具缺口：rebuild_capital_flow_table_and_track_breadth_sector_strength_orders_profit_cashflow

## 已经改进/沉淀到哪里
- **姿态先验**
  - 2026-09-15 2026-09-15_a_alex_review.json: not_applied_other_author
- **候选假设**
  - 2026-09-15 2026-09-15_a_alex_review.json: no_new_candidates_reinforces_XH-064_XH-118
- **命中审计**
  - 2026-09-15 2026-09-15_a_alex_review.json: user_transferred_wechat_comment_ocr_bound_to_official_handoff_and_sha256
- **工具/流程提案**
  - 2026-09-15 2026-09-15_a_alex_review.json: rebuild_capital_flow_table_and_track_breadth_sector_strength_orders_profit_cashflow

## 上期试验与失败跟进（先于新增试验，未记录不等于完成）

- `weekly-2026-09-11-baseline_no_kol`：验证本周及后续经济结果主要由既有 ★E、模式、资金与执行门解释，还是 KOL 确有超出少用资金的增量；建立可复放、同信息集、同风险暴露的 no-KOL/current 配对账。
  - 历史状态：needs_evidence_and_design；本周待复核；原复核日：2026-09-18。
  - 跟进结论（报告声明）：未记录，不能认定已完成
  - 回滚：本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-11；state sha256=3f44838feef9166e0a104aa877641cba6bbb96b0c22e843af7dcfdd049ba46c9。
- `weekly-2026-09-11-current_bounded`：检验现行有界 KOL 是否以更少尾部损失补偿等待、过期、语义歧义与错失机会；重点检验来源条件能否在第一次合法开仓前完成核实，而不是增加 post-morning 中性包数量。
  - 历史状态：needs_evidence_and_design；本周待复核；原复核日：2026-09-18。
  - 跟进结论（报告声明）：未记录，不能认定已完成
  - 回滚：本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-11；state sha256=3f44838feef9166e0a104aa877641cba6bbb96b0c22e843af7dcfdd049ba46c9。
- `weekly-2026-09-11-kol_challenger`：检验上游入口或模式集合是否造成局部最优：预登记竞价与盘中模式语义及点时完整机会集，在 authority=0 隔离队列观察正式 freeze 外候选，再比较 no-KOL/current/challenger。
  - 历史状态：needs_evidence_and_design；本周待复核；原复核日：2026-09-18。
  - 跟进结论（报告声明）：未记录，不能认定已完成
  - 回滚：本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。
  - 固定来源：`output/live/flywheel_change_ledger.jsonl`；复盘日期 2026-09-11；state sha256=3f44838feef9166e0a104aa877641cba6bbb96b0c22e843af7dcfdd049ba46c9。

## 整体框架试验槽位（待取证与设计，不是合格变更候选）

- 目标：验证本周及后续经济结果主要由既有 ★E、模式、资金与执行门解释，还是 KOL 确有超出少用资金的增量；建立可复放、同信息集、同风险暴露的 no-KOL/current 配对账。
  - 证伪条件：在完整逐笔合法成交与成本、同风险预算、跨窗口/OOS、剔除最大赢家并按来源聚类后，有界 KOL 仍显示不能由资格、执行或少用资金解释的稳定尾部或净收益改善，则推翻‘无增量’解释；证据不全保持不确定，不计 PASS。
  - 必要证据：按 live/paper 分别补齐 intent/claim、legal consume、broker/paper result、T+1/行情/拒绝理由、费用、资金流与每日结算 NAV；每个不可变 freeze 重建同整手、资金与退出的 baseline，并按 decision sha 与真实生效事件连接覆盖，过期或迟到不回填；逐笔报告净收益、尾部、回撤、平均与峰值暴露、现金时间积分、费用、避免下跌和错失上涨，按模式/日期/来源聚类；预注册等风险对照、OOS、多重比较及最低有效样本；当前只有一周标记样本时不得宣称 4/12 周验证
  - 回滚：本周未启动，现行基线不变。若另获研究门批准，先锁定代码、参数、数据版本与隔离路径；仅撤销该实验的明确变更并保留失败和恢复证据，不改正式账户、策略、安全或原 kill-switch。
  - 本次跟进（报告声明）：已逐项复核 2026-09-11 未启动槽位。本周早盘多次过期 neutral fallback、无可执行 ★E 或 freeze/价格约束支持‘结果首先由既有资格与执行解释’这一竞争解释；但缺配对反事实、完整费用/现金占用和结算，既不能判 no-KOL 胜出，也不能判 KOL 有超额。本次仅完成证据复核，实验仍未运行。
  - 负责人：xiaocao weekly review maintainer（隔离研究执行须另经研究门授权）；下次复核：2026-09-25。
- 目标：检验现行有界 KOL 是否以更少尾部损失补偿等待、过期、语义歧义与错失机会；重点检验来源条件能否在第一次合法开仓前完成核实，而不是增加 post-morning 中性包数量。
  - 证伪条件：点时合法的配对反事实显示错失上涨、费用和执行漏损抵消尾部收益，或改善只由一周、一个来源或一个赢家解释；若及时化只增加发布数量而不提高合法消费覆盖，也不支持改善命题。
  - 必要证据：统一记录 source occurrence/发布时间、received、request、模型开始/完成、review、published、valid_until 与 next legal consume；对 9 月 7 日窗口误判、9 月 11 日 post-morning 与 14:21 pause 做不可回放时间线审计，分开迟延、语义不可执行和确定性执行门；预先列出 exact source mode、trigger/falsifier 与 production 模式映射，保留连板评分未重估反证，不发明阈值或牺牲独立审核换速度；每次 pause 标记当时是否真有合法新增机会及重叠 T+1/未成交限制，衡量净增量而非 no-action 率
  - 回滚：本周只设计，不改调度、发布、TTL 或交易门。任何另行授权的隔离遥测先记录版本与恢复点；撤回遥测也不得放松来源复核、独立 review、freeze 绑定或资本门。
  - 本次跟进（报告声明）：已复核旧槽，未发现实际实验运行。新增反证是四个早盘 KOL review 超时，以及 9 月 16 日 10:25 pause 在 11:01 发布、13:25 过期，而可见 APP 引用到 13:26 已为 expired；9 月 17/18 日后续有效 neutral 读取说明覆盖可改善，但不是 alpha 或尾部收益证明。
  - 负责人：xiaocao weekly review maintainer（时钟与 lineage 实现须另行确认负责人）；下次复核：2026-09-25。
- 目标：检验上游入口或模式集合是否造成局部最优：预登记竞价与盘中模式语义及点时完整机会集，在 authority=0 隔离队列观察正式 freeze 外候选，再比较 no-KOL/current/challenger。
  - 证伪条件：在同本金、同整手/费用、同合法时点及流动性/T+1/退出约束、OOS 和完整失败样本下，挑战者未同时改善机会覆盖与风险调整表现，或优势依赖事后补榜、BJSE、模糊名字、单日赢家或不可复现评分版本，则拒绝；数据不足不作 PASS。
  - 必要证据：每来源与模式的请求/数据时间、版本 hash、完整行数、拒绝计数、readiness 与首次出现时间；预注册竞价、固定 9:31 与盘中候选研究层，不细扫最佳秒点或事后分数阈值，并锁定模式持有/退出和宽邻域稳健性；比较正式入口排除候选，分开 COLD 双 alpha 反证、真正未覆盖入口、身份/交易所/成交性硬拒绝；不改生产 freeze 或新增 live 候选；若讨论 v2，仍限小草本人、同日 freeze 内精确 mode-follow、COLD 非 UNKNOWN、非 BJSE、最多三槽且同模式一只
  - 回滚：本周未启动，研究候选 authority=0。启动前另经研究门批准并指定隔离输出和版本恢复点；停用研究读取不得触及正式账户、freeze、参数或资本 key，并保留反证与失败记录。
  - 本次跟进（报告声明）：已复核旧 challenger 槽，仍只有设计与来源语义，没有候选完整面板、合法成交反事实或 OOS 结果。保留 authority=0 入口/模式覆盖挑战者，但不能称现有过滤过严已经造成可实现损失，更不能以来源点名或涨幅反推新增候选。
  - 负责人：xiaocao weekly review maintainer（候选完整性研究须另经研究门授权）；下次复核：2026-09-25。

## 已自动落地的代码/配置变更
- none

## 证据来源
- 固定输入清单：scripts/flywheel_selfcheck.py, scripts/flywheel_sweep.py --json --top 30, reference/experience/distill_action_log.jsonl, kronos_screen/HYPOTHESES.jsonl, output/research/*, output/live/pnl_decompose.csv, output/research/paper_vs_market_*.md, output/live/posture_calibration.jsonl, output/live/exit_calibration.jsonl, reference/experience/research_protocols.yaml, output/research/runs/*/manifest.json, git status --porcelain
- KOL 固定复盘输入（仅观察，不增加自动落地权限）：output/live/kol_policy/context/*.context.json, output/live/kol_policy/decisions/*.json, output/live/book_b_live_execution/consumption.jsonl, output/live/book_b_live_execution/book_b_live_decisions.jsonl, output/live/book_b_live_execution/runs/*.json, output/live/kol_policy/account_risk/live_B.jsonl, output/live/paper_decision_support/consumption/*.json, output/live/paper_decision_support/consumption.jsonl, output/live/kol_policy/account_risk/risk_receipts/*.json, output/live/flywheel_change_ledger.jsonl, output/live/kol_policy/requests/*.json, output/live/kol_policy/source_verifications/*.json
- 提案数量：1
- 自动落地候选数量：0

## 验证
- data_doctor.py: PASS (no dirty-data findings)
- status.py --json: PASS (Book A/B/T readback; Book B equity 127928.97 with 0 open positions; Book T equity 29256.10 with 3 open positions and fresh valuation)
- strategy_protocols.py --check: PASS (3 protocols)
- pytest tests/test_weekly_deep_review.py: PASS (14 passed)
- bash -n scripts/auto_daily.sh: PASS
- git diff --check: PASS
- KOL evidence binding: PASS (10 selected refs current and inventory-known; Astra verified 670 unique inventory paths; parent independently reviewed conclusions)
- Astra semantic dispatch: PASS (gpt-6-astra xhigh, accepted dispatch and completed draft saved)
- KOL publication: NOT RUN (weekly review_only evidence does not authorize a new decision)

## 回滚
- 如果本周有提交：`git revert <commit>`

## 飞轮健康度
- 总体在转：True
- 策略飞轮：open；待处理 PASS=[]
- 知识飞轮：候选 139 / 已测 10 / 已退役 5 / 最老未测 2025-01-09

## 提案文件
- .scratch/weekly-deep-review/2026-09-18/instrumentation-contract-capital-flow-breadth-2026-09-18.md

## 机器审计明细
```json
{
  "scoreboard": {
    "action_log_rows": 85,
    "candidate_assertions": 205,
    "candidate_to_tested": 0.07,
    "candidates_passed": 1,
    "candidates_retired": 5,
    "candidates_tested": 10,
    "candidates_total": 139,
    "candidates_untested": 129,
    "dedup_ratio": 0.68,
    "instrumentation_todos": 53,
    "median_recurrence": 1,
    "oldest_untested": "2025-01-09",
    "oldest_untested_age_days": 617,
    "tested_to_pass": 0.1,
    "transcripts_distilled": 85
  },
  "pass_evidence": [],
  "pre_existing_dirty_count": 4,
  "pre_existing_dirty_sample": [
    " M src/xiaocao/live/app_test_window.py",
    "?? .scratch/book-b-morning-20260916-review/",
    "?? .scratch/kol-netdisk-e51919c15179ed8d-content-audit.json",
    "?? tests/test_app_preopen_grant.py"
  ],
  "kol_system_review_status": "pending_analysis",
  "kol_inventory_sha256": "e1b0829d19f473d45482df1a4fdd1a25056fd1cb1ed34cab59d0b6caae3dec39",
  "kol_audit_feedback": {
    "consumption": {
      "live": {
        "book_counts": {
          "B": 100
        },
        "consumption_container_count": 81,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 7,
          "kol-b-live-opening-20260916-pause-adds-329fb25c-v1": 1,
          "kol-b-live-sparse-20260916-1025-pause-7878186a-v1": 1,
          "kol-b-live-sparse-20260916-1325-neutral-3510a357-v1": 25,
          "kol-b-live-sparse-20260917-1025-neutral-d4b2fe7f-v1": 6,
          "kol-b-live-sparse-20260917-1325-neutral-b4cc5ae7-v1": 21,
          "kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1": 7,
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
        "evidence_sha256": "870013013aa3fd181de0f25521d9d3be590f4767c45a523cdb7e80e75a29419a",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 71,
        "legacy_file_count": 11,
        "missing_consumption_clock_count": 29,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 0,
        "paper_terminal_status_counts": {},
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 71,
        "record_count": 100,
        "reported_execution_status_counts": {},
        "skip_record_count": 0,
        "source_file_count": 22,
        "status": "read",
        "unbound_decision_reference_count": 77
      },
      "paper": {
        "book_counts": {
          "B": 9
        },
        "consumption_container_count": 9,
        "decision_counts": {
          "kol-b-both-sparse-20260915-1325-pause-adds-94a394-v1": 1,
          "kol-b-paper-sparse-20260916-1325-neutral-3510a357-v1": 1,
          "kol-b-paper-sparse-20260917-1325-neutral-b4cc5ae7-v1": 1,
          "kol-b-precheck-20260908-1428-astra-neutral-v1": 1,
          "kol-b-sparse-20260907-1430-astra-neutral-v1": 1,
          "kol-b-sparse-20260909-1325-astra-neutral-38a3f375-v1": 1,
          "kol-b-sparse-20260910-1055-astra-neutral-12b5dc0e-v1": 1,
          "kol-b-sparse-20260914-1325-pause-adds-5903d480-v1": 1,
          "kol-xiaocao-sunday-pilot-20260906-reviewed-v2": 1
        },
        "evidence_sha256": "8379222536b9b4d719bb283e52bd7e14afd05d6eb102c92d8c2f9e9ae530e774",
        "exit_request_record_count": 0,
        "hash_bound_record_count": 9,
        "legacy_file_count": 0,
        "missing_consumption_clock_count": 9,
        "paper_claims_without_terminal": 0,
        "paper_scaled_slot_count": 0,
        "paper_slot_count": 8,
        "paper_terminal_status_counts": {
          "bought": 5,
          "no_buy": 4
        },
        "paper_zero_slot_count": 0,
        "production_hash_bound_record_count": 9,
        "record_count": 9,
        "reported_execution_status_counts": {},
        "skip_record_count": 4,
        "source_file_count": 18,
        "status": "read",
        "unbound_decision_reference_count": 9
      }
    },
    "execution_verification": "not_performed",
    "profit_attribution": "not_established",
    "published_decision_count": 37,
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
        "conclusion": "已逐项复核 2026-09-11 未启动槽位。本周早盘多次过期 neutral fallback、无可执行 ★E 或 freeze/价格约束支持‘结果首先由既有资格与执行解释’这一竞争解释；但缺配对反事实、完整费用/现金占用和结算，既不能判 no-KOL 胜出，也不能判 KOL 有超额。本次仅完成证据复核，实验仍未运行。",
        "disposition": "continue",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "eb3e616985491b7925af6312a091130a74124cabb1c74636ba318297c6449445"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "e8a6c26e7f6726408d98541fde3d438c2a6c8c83681715ebb41549b45c8d2018"
          },
          {
            "path": "output/live/book_b_live_execution/runs/2026-09-17.json",
            "sha256": "e09c1c65486cbb07457c16de481a7cdc70cd46bb34ebc5c1ae5d31340e8e184c"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "baseline_no_kol",
      "next_review": "2026-09-25",
      "objective": "验证本周及后续经济结果主要由既有 ★E、模式、资金与执行门解释，还是 KOL 确有超出少用资金的增量；建立可复放、同信息集、同风险暴露的 no-KOL/current 配对账。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（隔离研究执行须另经研究门授权）",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "eb3e616985491b7925af6312a091130a74124cabb1c74636ba318297c6449445"
      },
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
        "conclusion": "已复核旧槽，未发现实际实验运行。新增反证是四个早盘 KOL review 超时，以及 9 月 16 日 10:25 pause 在 11:01 发布、13:25 过期，而可见 APP 引用到 13:26 已为 expired；9 月 17/18 日后续有效 neutral 读取说明覆盖可改善，但不是 alpha 或尾部收益证明。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "eb3e616985491b7925af6312a091130a74124cabb1c74636ba318297c6449445"
          },
          {
            "path": "output/live/book_b_live_execution/book_b_live_decisions.jsonl",
            "sha256": "e8a6c26e7f6726408d98541fde3d438c2a6c8c83681715ebb41549b45c8d2018"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-opening-20260916-pause-adds-329fb25c-v1.json",
            "sha256": "88f4078d1d712a69a8ba52d8c0cf3ff89d66bd29bb85bdb12364a244e58799e5"
          },
          {
            "path": "output/live/kol_policy/decisions/kol-b-live-sparse-20260918-1325-neutral-3ae43f5a-v1.json",
            "sha256": "31402b91fc41850b048f6ca9956943455c753347c3307e1af458576604aad295"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "current_bounded",
      "next_review": "2026-09-25",
      "objective": "检验现行有界 KOL 是否以更少尾部损失补偿等待、过期、语义歧义与错失机会；重点检验来源条件能否在第一次合法开仓前完成核实，而不是增加 post-morning 中性包数量。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（时钟与 lineage 实现须另行确认负责人）",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "eb3e616985491b7925af6312a091130a74124cabb1c74636ba318297c6449445"
      },
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
        "conclusion": "已复核旧 challenger 槽，仍只有设计与来源语义，没有候选完整面板、合法成交反事实或 OOS 结果。保留 authority=0 入口/模式覆盖挑战者，但不能称现有过滤过严已经造成可实现损失，更不能以来源点名或涨幅反推新增候选。",
        "disposition": "refine",
        "evidence_refs": [
          {
            "path": "output/live/flywheel_change_ledger.jsonl",
            "sha256": "eb3e616985491b7925af6312a091130a74124cabb1c74636ba318297c6449445"
          },
          {
            "path": "output/live/kol_policy/context/3ae43f5a0bc1b811bbd78c701d4fe0f739787095bc212c093713b24249384a6e.context.json",
            "sha256": "4ef3c7f92a006091fbb737cee07ea4fe9e1bad61b23331529cde0a138c69f1b1"
          }
        ],
        "status": "reviewed"
      },
      "follow_up_required": true,
      "id": "kol_challenger",
      "next_review": "2026-09-25",
      "objective": "检验上游入口或模式集合是否造成局部最优：预登记竞价与盘中模式语义及点时完整机会集，在 authority=0 隔离队列观察正式 freeze 外候选，再比较 no-KOL/current/challenger。",
      "origin_review_date": "2026-09-11",
      "owner": "xiaocao weekly review maintainer（候选完整性研究须另经研究门授权）",
      "prior_review_evidence": {
        "path": "output/live/flywheel_change_ledger.jsonl",
        "sha256": "eb3e616985491b7925af6312a091130a74124cabb1c74636ba318297c6449445"
      },
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
