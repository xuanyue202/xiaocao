# 小草运营契约（Operating Contract, SSOT）

**版本**：1.8
**状态**：现行
**适用范围**：所有 paper / 未来 real 的实盘环（live_recommend → paper_record → live_monitor → eod）与回测
**关联实现**：`src/xiaocao/live/safety.py`、`src/xiaocao/live/intelligence_policy.py`、`src/xiaocao/strategy/trend_rules.py`、`kronos_screen/scripts/{paper_record,settle_book_a,settle_book_t,decompose_pnl,quality_governor}.py`、`scripts/live_monitor.py`
**回归测试**：`tests/test_operating_contract.py`
**借鉴**：QuantDinger `docs/SIGNAL_EXECUTION_STANDARD_CN.md`（契约 SSOT 结构）+ `docs/agent/MCP_SETUP.md`（paper-only 默认 / 双钥匙 live gate）

> 本文件是**单一真源（SSOT）**。`xiaocao-trading` skill 与各 automation **引用**本契约，不重复其中的口径。任何口径变更 **MUST** 同步本文件版本号与第 12 节修订记录。

---

## 1. 目的

实盘环由多个**全新上下文的 agent**（5 个 Codex cron）轮流操作。若口径不统一，会重演 iteration-7 的教训：book A（验证口径）与 book B（实盘 stop 口径）漂移（曾 -4,191）。本契约把"agent 写什么、确定性脊柱如何执行、回测与实盘如何对齐、资金动作如何被守门"固化为不可变法律。

---

## 2. 架构原则：LLM 不进确定性回路

| 层 | 负责 | 是否有 LLM |
|----|------|-----------|
| **确定性脊柱** | data / fill / stop / 记账(book A/B/T) / 安全 / 契约校验 | **否**——纯确定性代码，回测与实盘**同一份** |
| **Agent 皮层** | 判断：每日 posture、异常分诊、强持有例外、研究方向 | 是——结构化包进、结构化决策出（入审计日志） |
| **Benchmark / Watchlist / Research Cohort 中间层** | `reference/experience/cohorts/*.yaml`（定义）/ `output/cohorts/cohort_snapshots.jsonl`（逐日快照）/ `output/research/*.jsonl`（护栏输入）：承接 raw pool、老师点名战果、本地标杆买入与待研究观察名单 | 否——**authority=0**，只供复盘、观察、`research_run.py`，不直接进买入/卖出/记账 |
| **复利记忆** | cache.db / decision_journal.jsonl / HYPOTHESES.jsonl / training_rows / model（注：`state.db` 可查询投影**尚未实现**——当前"查询当前状态"由 `status.build_digest` 直接装配 jsonl，非 SQL） | 否 |
| **判断先验（小草蒸馏）** | `reference/experience/distilled/*.json`（逐篇结构化提取）/ `docs/XIAOCAO_PLAYBOOK.md`（道-法-术-纪律 + 实时盘面判断模型）/ `reference/experience/REGIME_TIMELINE.md`（dated posture）/ `reference/experience/xiaocao_hypotheses.jsonl`（**candidate** 假设账本，非 verdict） | 是——**仅** agent 皮层判断/叙述先验；**无脚本读取**，不进脊柱 |

**MUST NOT**：让 agent 直接计算成交价、改账本余额、决定是否真实下单。这些只能由脊柱确定性执行；agent 仅产出"判断"，落入决策日志。

**MUST NOT（判断先验）**：不得让 playbook / REGIME_TIMELINE / xiaocao_hypotheses.jsonl 的先验进入 fill/stop/记账/安全，或据此**自动调任何 param/threshold/profile/model**。candidate 假设**不是 verdict**，对脊柱权威 = 0；唯一升级路径 = 过 `research_run.py` 护栏 → `kronos_screen/HYPOTHESES.jsonl` → §10 人工门。

**MUST NOT（cohort 中间层）**：不得把 `benchmark/watchlist/research cohort` 成员直接当成实盘买入。cohort 可以证明“值得观察/值得研究/是老师或本地标杆”，但一条 cohort 只有通过 `research_run.py` 护栏并经过 §10 人工门，才能升级为 emitted strategy 或 param 变更。2026-06-30 人工门已将 raw-qibao top10 + 电子/20cm 的 `high_open_watch` 6%-10% 子桶和 `limitlike_watch` 升级为 **Book B 模拟盘** emitted modes（`高开标杆起爆` / `强攻标杆起爆`）；这不改变实盘两钥匙边界。

- **运行状态语义**：自动化必须分别记录 `deterministic_status` 与 `supporting_health`。主链脚本成功但 data-health、posture 或 agent-review 支持层不完整时，总状态是 `degraded`，不能伪装成全健康 `succeeded`；支持层降级也不能反写成确定性成交/记账失败。
- **账本身份是会计主键**：`positions.jsonl` 与 `paper_trades.jsonl` 的每一行都必须显式写合法 `book=A/B/T`，所有现行写入端缺失时 fail-closed。读取端的历史兼容默认不能充当修复；旧账只能由专属 writer source 或唯一匹配的 code/date/shares/price/PnL 证明后回填，并记录前后 hash 的 repair audit。

---

## 3. Book A — 验证参考口径（永不被监控）

- **口径**：买入 = 与 Book B 对齐的最终实际纸面成交价 `book_b_fill[D]`（同一批 fillable picks，同一套 9:30-9:31 VWAP/limit/retry 入场）；卖出 = **下一交易日收盘** `close[D+1]`；**无 stop**。
- **唯一实现**：`paper_record._record_book_a`（建仓，复用 Book B `entry_price_basis`/fill metadata）+ `settle_book_a.py`（盘后结算，幂等）。
- **角色**：纯会计账本 + **kill-switch 传感器**；永不被 `live_monitor` 触碰或 stop 管理。
- **MUST**：book A 行（`book="A"`）与 book B 互不阻塞建仓；settle 只用 `close[D+1]`，幂等。
- **A/B 归因口径**：累计 account realized 差只是一条会计信息，样本数/仓位/结算进度不同时不得解释为止损帮助或伤害。退出层描述性比较只纳入同 `code+entry_date+entry_price+shares` 且 A/B 均已 closed 的逐仓配对，以 `realized_pnl / entry_cash_out` 的归一化收益计算 B-A pp，并同时披露 eligible n 与 share/price/open/missing 排除数；统计本身不构成因果结论。

## 4. Book B — 实盘策略口径（分阶段出场）

- **建仓**：`paper_record`（见第 5 节成交模型）。
- **AI 情报因子（paper-only P2）**：`paper_record.py --intelligence-trade on` 消费已经落盘的结构化 `agent_review`，在最新 `signal_snapshots.jsonl` 候选池内按 `rank_score + agent_short_score × ai_score_bonus` 重排 Book-B 纸面买入 slot；`agent_short_score >= ai_buy_threshold` 的非基础 ★B 候选可参与替换。没有 `agent_review` 时必须退化为原始 `vb_star` 选择。关键词 `keyword_score` / 一句话舆情永不参与买入排序。
- **AI hard-veto**：只认 `intelligence_evidence.HARD_VETO_TAXONOMY` 中的明确事件类型，且需模型写入 `veto_flags`、`severity` 达 high/critical、`confidence >= ai_veto_confidence`、未过短线时效或标记 ongoing。命中后 Book-B 纸面买入跳过并写 `paper_skips.jsonl` 的 `AI_HARD_VETO`；非法 event_type / 低置信 / 低严重度不生效，避免关键词一票否决。Evidence freeze 覆盖当天候选池和当前 open Book-B 持仓；同日缓存只在新鲜 TTL 内复用，过期后刷新素材，避免盘中新利空被旧缓存遮蔽。
- **出场分阶段**（`live_monitor`）：
  - **AI_EVENT_RISK_EXIT**：持仓股票若当天结构化 `veto_flags` 命中 hard-veto，且不处于 T+1，则触发尽早卖出；仍受跌停无买盘等流动性执行约束。
  - **盘中仅执行** `HARD_STOP`（peak→now 回撤 ≥ **8%** 且无强持有理由）或流动性逃逸。
  - **普通 trailing / composite 恶化盘中只诊断**（状态列 `defer:<reason>`，alerts 记 `SELL_DEFERRED`）→ **14:55 纪律 pass 统一执行**，出场对齐 next_close 参照。
  - **T+1**：建仓日不可卖（`t1_blocked`，诊断用）。
  - **流动性**：触发卖出但跌停无买盘 → 记 `SELL_BLOCKED / LIMIT_DOWN_NO_BID`，**保持持仓**，不更新 cash/realized_pnl/trades。
- **收盘任务与单写者**：14:25 是独立风险预检，只立即执行盘中已获授权的 HARD_STOP / AI_EVENT_RISK_EXIT 等，不等待 14:55；14:55 是独立且唯一的 soft-exit 收盘纪律 pass。所有 paper-record / monitor / settle / repair 写者共享唯一 `paper_ledger.lock`，必须在锁内重载并提交，重叠 agent 只能观察前一写者结果，不能重复 SELL。收盘 positions/account/trades 三文件提交先持久化 `.ledger_txn/pending.json` 与目标快照；中断后下一写者幂等补完，未恢复事务由 data doctor 报 CRITICAL，禁止用半提交账本评估。
- **强持有例外**（抑制 trailing 出场）：接力/连板 或 xcjw≥300 或 jsjl>0；近涨停（≥99.7% up_price）；成为领涨且 pct≥8% 且近日高（≥99.5%）。
- **profile**：v5 = 5 日 / dd 2%；v6 = 3 日 / dd 0.5%（更激进，需前瞻验证）。hard floor 两者均 8%。

## 4b. Book T — 趋势模拟口径（paper-only，独立生命周期）

- **建仓**：`paper_record.py --trend-only` 调 `strategy.trend_rules.generate_trend_picks`，从当前主线大类中选少量大票/中军候选，写入 `positions.jsonl` 的 `book="T"` 行；同 code 可同时有 B/T 两行，互不阻塞、互不 net。候选分为 `aligned / neutral / external`：电子、半导体、存储、光电、元器件、通信、机器人等与当前小草主线相关者优先；中性候选只作保持趋势仓位的兜底；银行/保险/证券/医药/白酒等外部旧方向是 `external`，不得作为新趋势买入。
- **账户**：`paper_account_T.json`，默认初始资金 = `initial_capital × TREND_BUDGET_RATIO`；统一 `paper_trades.jsonl` 记录 `book:"T"`。
- **状态快照一致性**：`status.py` 的持仓数量只取 `positions.jsonl` open T 行。`paper_holdings_T.json` 只有在日期、`(code,entry_date,shares)` 身份集和 account totals 全部匹配时才有估值权；否则 `equity` 降级为 cash + open entry cost，`unrealized_pnl=N/A` 并显式给出 `stale/mismatch/missing`，禁止跨版本拼接。
- **出场 / 换股**：`live_monitor.py --book T` 和 `settle_book_t.py` 只认冻结趋势参数：`TREND_TRAIL_DD` 宽回撤；方向错配和 `TREND_REBALANCE_R` 低换手到期都不在 EOD 单边卖出。已持仓若被分类为 `external` 且过 T+1，或达到低换手 rebalance 周期，下一次 morning 只有在 `paper_record.py --trend-only` 已找到可成交替代候选时，才按 `TREND_POSTURE_MISMATCH` / `TREND_REBALANCE_R` 做成对 SELL+BUY；无替代则继续持有，避免趋势袖子空仓断档。普通排名变化不触发换仓，避免手续费和噪音换手。**不得调用** Book B 的 `strong_hold_reason` / composite 逻辑，也不得让“方向还在”这类皮层判断抑制 B 的止损。
- **流动性事实优先**：`SELL_BLOCKED / LIMIT_DOWN_NO_BID` 是执行事实；14:55 后同日同 `book+code+entry_date` 被阻卖时，`settle_book_t.py` 必须保持 open，禁止用理论收盘价补记 SELL。`data_health.blocked_sell_executions` 对违反此不变量的账本报 CRITICAL。
- **评估**：Book T 不进入 `forward_eval.py -> training_rows.parquet -> continuous_optimize.py` 的短线 per-trade A/B/C/D 口径；趋势评估只走 `trend_guards` / `trend_optimize` 的复利、回撤、换手、vs-beta 仪器。`trend_optimize.py --record` 只能把 changed verdict 写入 `kronos_screen/HYPOTHESES.jsonl`，不得改 `TREND_*` 参数。
- **命名空间**：`signal_snapshots.jsonl` 的唯一键是 `(date, code, is_live, book)`；缺 `book` 的旧行默认 B。`data_health` / `contexts` / `forward_eval` 均必须保留 book 维度，避免 B/T 同票同日被误判重复或互相覆盖。

## 5. 成交模型（真实，非最坏价）

- 初始限价 `L = min(open[D] × (1 + 0.5%), basket_price)`；开盘窗口（默认 09:30–09:31）结算后，若窗口最低价触达 `L`，**fill = min(窗口VWAP, L)**。
- `basket_price` **仅为放弃线**，**MUST NOT** 作为成交假设（旧行为按 basket 记成交=虚构 ~1.9%/笔滑点，已废）。
- 窗口最低价 > `L` → 先视为初始限价未成/可能被交易所价格笼子拦截，再检查窗口最后价（实时补单代理）：若 `last <= basket_price`，按 `last` 成交并记录 `retry_realtime_after_limit_reject`；若 `last > basket_price` 或缺少可用实时价 → **SKIP**（`paper_skips.jsonl`，`LIMIT_NOT_REACHED` + `skip_detail`，**不静默丢弃**）。
- 无窗口数据 → 回退到 L（`fill_fallback`）。
- 唯一实现：`paper_record._fill_price_from_window`。
- **数据源单一性（OHLCV 故意不接公共源 fallback）**：止损/peak-dd 依赖的分钟线 OHLCV **只**来自专有 API（`client.minute_line`）。**MUST NOT** 把公共源（akshare/腾讯等）价格接入 live 止损路径：不同复权/时间戳/坏tick 会算出不同的 peak/dd，使 book B 与验证 next-close 口径及 API 喂的回测**静默漂移**——正是 data_health 要抓的"真的谎言"。OHLCV 不可得时应 **fail-safe（持有/跳过）**，而非用二手数据动作。公共源仅允许用于**带 provenance 标记、经对账的研究/回填工具**，且 book A/B 记账永不读 `source='public'`。
- **四指数基准完整性**：`refresh_daily_cache.py` 每日必须把上证、深成指、创业板指、中证1000 与持仓/信号一起做分钟重建，并按显式 `--date` 选择该日信号。`forward_eval` 的 `market_return_pct` 与 paper-vs-market 均要求四项齐全；任一缺失时聚合值/超额收益为 N/A，禁止把缺失当 0 或用部分指数冒充四指数均值。
- Book T 使用同一成交模型与同一专有 OHLCV 边界；`basket_price` 仍只是放弃线。

## 6. 仓位与资金

- `deploy_ratio` 默认 **0.5**（留 dry powder）；`max_total_exposure_ratio` 默认 **0.67**；等权滚动现金；整 100 股；单边费率 **1bp**。
- 被 quality-governor 过滤的 slot **留现金、不再分配**（保守）。
- Book T 默认预算为独立 T 账户 `TREND_BUDGET_RATIO=30%`、目标 `TREND_TOP_M=3` 个 slot；这只是 paper 仪器参数，不是已验证 alpha。Book T 的目标是“趋势袖子尽量保持仓位”，不是每日追排名；换股要有主线错配或 rebalance 到期证据，并记录估算往返手续费。

## 7. Quality Governor（默认 shadow）

- `primary_score`（按 mode）：起爆→`jssb`；接力→`xcjw + 0.5·max(jsjl,0)`；N字/孕线低吸→`xcjw + 0.6·cjs`；其余低吸→`xcjw + 0.8·cjs`。
- 阈值 `PRIMARY_THRESHOLD = 150`；`primary < 150` → `weak_primary`。`p_score ≤ -2` → `p_tail_warning`（仅警告）。
- 模式：`off`（忽略）/ `shadow`（默认，仅审计 `quality_governor_audit.jsonl`，不拦截）/ `on`（弱 slot 留现金）。唯一实现 `quality_governor.py`。

## 8. Kill-switch（性能型，唯一部署控制）

- 依据 book A 近 5 个出场日累计收益：`< -3%` → book B deploy **减半**；`< -5%` → book B **停买**。
- **传感器常活**：book A 记账与数据采集**永不**因 kill-switch 停止。唯一实现 `paper_record._kill_switch_factor`。
- 指数/regime deploy gate 已回测全败 train+test 一致性（`backtest_deploy_gate.py`），故**不接任何指数 regime gate**；性能 kill-switch 是唯一 deploy 控制。
- Book T 不新增第二部署闸；它独立 paper 运行，用 trend_guards 评估，不反向改动 Book B。

## 9. 双钥匙资金动作边界（real-capital，借 QuantDinger 双钥匙）

- **paper / sensor / research / simulation 永远放行**（research 永不被资金门阻塞，传感器永不停）。
- **real_capital 必须同时**：
  1. env `XIAOCAO_LIVE_TRADING_ENABLED=true`；
  2. 签名授权 `output/live/live_authorization.json`（HMAC 对 `XIAOCAO_LIVE_SIGNING_KEY` 校验，**agent 无法自签**——签名密钥由人持有，automation 环境不携带；由交互式 `scripts/authorize_live.py` 铸造）。授权**带 scope（max_notional / side / code 白名单）与到期**。
- 任一缺失/签名被篡改（含非 ASCII 签名）/过期/越权/**或越权属性缺省**（如限定 max_notional 却未指定 notional、限定 side/code 却为 None）→ **硬拒**（fail-closed）。
- 审计：real_capital **ALLOW 必须可持久审计**——若审计写失败则转为 DENY（不下不可审计的真实单）；DENY/always-allowed 行为 best-effort（审计永不让交易回路崩溃）。`require_capital_action` 拒绝时**只**抛 `CapitalActionDenied`。
- 唯一实现 `src/xiaocao/live/safety.py`；真实下单 **MUST** 经 `require_capital_action(...)`，仅在 ALLOW 时下单。
- **现状**：尚无 real-capital 调用点（paper-only）；本节是 paper→real 的结构缝，使切换=配置翻转而非重构。

## 10. 快速探索期的自动迭代 / 升级策略（agent 皮层）

- **只上报真实异常**：脚本失败、缺预期输出、`候选股 NONE`、缺 paper-record 输出、对账 MISMATCH、`HARD_STOP` 触发、现金不足、可疑数据、**③ 策略飞轮 `blocked`**（有 PASS 裁决待应用却无 actuator——验证过的 edge 闲置）。
- **探索期目标**：当前无 real-capital；核心目标是提升收益率和验证效率。weekly deep review 可以在 paper/simulation/research/tooling 范围内自动改代码/参数并提交，但任何改动都必须有明确归因证据，不能想当然。
- **自动改动硬门槛：`evidence_bundle`**。没有完整 `evidence_bundle` 的事项只能 `PROPOSAL_ONLY`，不得 `AUTO_APPLIED`。每个 bundle 必须写清：
  `problem_observed`、`attribution`、`evidence_artifact`、`baseline_vs_variant`、
  `overfit_check`、`change_scope`、`rollback`。
- **AUTO_APPLIED 候选格式**：weekly finalize 必须收到至少一个 auto-apply candidate（plan 内或 `--auto-apply-candidate` JSON/JSONL），字段包括 `id`、`title`、`source`、`recommended_change`、`evidence_bundle`。脚本会校验 source 是否属于固定输入清单、bundle 是否完整、validation 是否不含失败标记；校验失败不得提交为 `AUTO_APPLIED`。
- **固定输入清单**：自动改动只能来自 weekly plan 的固定输入：`flywheel_selfcheck.py`、`flywheel_sweep.py --json --top 30`、`distill_action_log.jsonl`、`kronos_screen/HYPOTHESES.jsonl`、`output/research/*`、`pnl_decompose.csv`、`paper_vs_market_*.md`、`posture_calibration.jsonl`、`exit_calibration.jsonl`、`git status --porcelain`。固定输入之外的发现一律写 proposal 等用户确认。
- **允许自动改**：paper/simulation 策略参数、emitted modes、Book B/T 模拟策略、研究脚本、报告字段、cohort 规则、模型配置、蒸馏/action-log/schema/observability 工具。策略收益类改动必须有 PASS / fill-aware PASS / baseline-vs-variant 明确改善，并说明不过拟合证据；工具类改动必须能归因到具体审计/验证缺口。
- **不得自动改**：账户历史、成交账本、原始缓存、数据口径真相源、安全校验、real-capital 授权逻辑、live authorization、手工改账。即使未来上小资金，真实资金边界仍走双钥匙。
- **dirty-file 边界**：weekly 开始时记录 `git status --porcelain`。运行前已 dirty 的文件不得自动修改；若证据明确指向该文件，周报第一屏写 `NEEDS_HUMAN_CONFIRMATION`，创建 `.scratch/weekly-deep-review/...` proposal，等待用户明确确认。
- **提交与审计**：weekly finalize 写 `output/live/weekly_review_YYYY-MM-DD.md`、追加 `output/live/flywheel_change_ledger.jsonl`、只 stage allowlist 文件并直接提交当前分支。`AUTO_APPLIED` 和 `PROPOSAL_ONLY` 都可以 commit；commit body 必须列 validation、报告路径、rollback。不得 `git add -A`。
- **非异常（正常）**：`SELL_DEFERRED`（盘中只诊断）、`T+1_blocked`、非交易日 skip、book A 单独结算、Book T 无候选/无到期结算、**③ 策略飞轮 `open`**（无 PASS 可应用，策略正确地冻结，无需动作）。
- EOD 是**盘后审计**，非新多空判断：强调执行纪律、A/B 证据、数据采集健康、账户一致性、未决风险。

## 11. 契约不变量（可执行回归 → `tests/test_operating_contract.py`）

- [x] paper/sensor/research 永远放行；unknown kind 默认拒。
- [x] real_capital 缺任一钥匙 / 签名篡改 / 过期 / 越权 / 超额 → 拒；双钥匙 in-scope → 放行；每个决定入审计。
- [x] `require_capital_action` 拒时抛 `CapitalActionDenied`。
- [x] 成交 ≤ basket 放弃线（`_fill_price_from_window`）；窗口最低价 > L 时，实时价仍在 basket 内则补单成交，否则 SKIP。
- [x] book A/B fixture 回放：同组 picks 过 A/B，realized 差 **完全等于出场口径差**（逐仓可归因，无记账漂移）；无 stop 触发时 book A == book B（消灭 iteration-7 的 -4,191 漂移）。`tests/test_operating_contract.py::test_ab_replay_*`
- [x] Book T snapshot/account/monitor key 均带 `book` 命名空间；B/T 同票同日不互相覆盖；T 宽止损不调用短线 strong-hold/composite。
- [ ] （后续）settle_book_a 只用 next_close 且幂等；decompose_pnl 三项金额求和 = account realized_pnl（容差=取整）。

## 12. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-06-20 | 首版：架构原则 + book A/B 口径 + 成交模型 + 仓位 + governor + kill-switch + **双钥匙资金边界** + 异常策略 + 不变量。 |
| 1.1 | 2026-06-21 | §2 登记「判断先验（小草蒸馏）」复利记忆层（playbook / REGIME_TIMELINE / distilled / xiaocao_hypotheses.jsonl）+ 新增 MUST NOT：先验不进脊柱、不自动改参，candidate≠verdict。能力层接入 SKILL.md「Xiaocao Judgment Playbook」节，与 FLYWHEEL.md「判断先验→候选假设」两层假设模型对齐。 |
| 1.2 | 2026-06-30 | §2 增加 Benchmark/Watchlist/Research Cohort 中间层：承接老师点名、本地标杆与 raw pool 观察样本，authority=0；明确 cohort 不直接进 paper-buy/确定性脊柱，唯一升级路径仍为 research_run 护栏 + §10 人工门。 |
| 1.3 | 2026-06-30 | 记录 raw-qibao high-open 6%-10% 与 limitlike 子桶的 §10 paper-only 升级边界；仍无实盘授权。 |
| 1.4 | 2026-07-01 | Book T 趋势模拟仓上线：`trend_rules.py` 候选、`paper_record.py --trend-only`、`paper_account_T.json`、`live_monitor.py --book T`、`settle_book_t.py`；snapshot/data_health/context/forward_eval key 升级为 book-scoped；`trend_optimize.py` 接入 `trend_guards` 复利/dd/换手评估并与短线 `continuous_optimize.py` 分离。 |
| 1.5 | 2026-07-02 | 快速探索期 weekly deep review 自动迭代规则：evidence_bundle 硬门槛、固定输入清单、dirty-file 显式确认、proposal/weekly report/change ledger、allowlist staging/current-branch commit；允许 paper/simulation 自动改动，仍禁止账户/缓存/安全/real-capital 授权自动改。 |
| 1.6 | 2026-07-02 | Book T 候选与换股口径细化：新仓按 `aligned/neutral/external` 分层，外部旧方向不买；已持有 `external` 过 T+1 后按 `TREND_POSTURE_MISMATCH` 换出，普通排名变化只等低换手 rebalance，保持趋势袖子仓位但避免银行/保险等防守方向被误当主线。 |
| 1.7 | 2026-07-03 | Book T 错配/低换手 rebalance 改为 morning 成对切换：EOD 不再单边卖出 `external` 或 rebalance-due 行；早盘只有出现可成交替代候选时才 SELL+BUY，同步记录 `paired_morning_switch`，无替代则保持趋势暴露。 |
| 1.8 | 2026-07-05 | AI 情报因子 P2 接入 Book-B 纸面交易：结构化 `agent_review` 短线分参与候选池重排，taxonomy hard-veto 可跳过买入并触发 T+1 后 `AI_EVENT_RISK_EXIT`；关键词舆情仍只作诊断，real-capital 边界不变。 |
