# 小草运营契约（Operating Contract, SSOT）

**版本**：1.0
**状态**：现行
**适用范围**：所有 paper / 未来 real 的实盘环（live_recommend → paper_record → live_monitor → eod）与回测
**关联实现**：`src/xiaocao/live/safety.py`、`kronos_screen/scripts/{paper_record,settle_book_a,decompose_pnl,quality_governor}.py`、`scripts/live_monitor.py`
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
| **确定性脊柱** | data / fill / stop / 记账(book A/B) / 安全 / 契约校验 | **否**——纯确定性代码，回测与实盘**同一份** |
| **Agent 皮层** | 判断：每日 posture、异常分诊、强持有例外、研究方向 | 是——结构化包进、结构化决策出（入审计日志） |
| **复利记忆** | cache.db / state.db / decision_journal / HYPOTHESES / training_rows / model | 否 |

**MUST NOT**：让 agent 直接计算成交价、改账本余额、决定是否真实下单。这些只能由脊柱确定性执行；agent 仅产出"判断"，落入决策日志。

---

## 3. Book A — 验证参考口径（永不被监控）

- **口径**：买入 = 信号日开盘参考价 `open[D]`；卖出 = **下一交易日收盘** `close[D+1]`；**无 stop**。
- **唯一实现**：`paper_record._record_book_a`（建仓，`entry_price_basis="open_reference"`）+ `settle_book_a.py`（盘后结算，幂等）。
- **角色**：纯会计账本 + **kill-switch 传感器**；永不被 `live_monitor` 触碰或 stop 管理。
- **MUST**：book A 行（`book="A"`）与 book B 互不阻塞建仓；settle 只用 `close[D+1]`，幂等。

## 4. Book B — 实盘策略口径（分阶段出场）

- **建仓**：`paper_record`（见第 5 节成交模型）。
- **出场分阶段**（`live_monitor`）：
  - **盘中仅执行** `HARD_STOP`（peak→now 回撤 ≥ **8%** 且无强持有理由）或流动性逃逸。
  - **普通 trailing / composite 恶化盘中只诊断**（状态列 `defer:<reason>`，alerts 记 `SELL_DEFERRED`）→ **14:55 纪律 pass 统一执行**，出场对齐 next_close 参照。
  - **T+1**：建仓日不可卖（`t1_blocked`，诊断用）。
  - **流动性**：触发卖出但跌停无买盘 → 记 `SELL_BLOCKED / LIMIT_DOWN_NO_BID`，**保持持仓**，不更新 cash/realized_pnl/trades。
- **强持有例外**（抑制 trailing 出场）：接力/连板 或 xcjw≥300 或 jsjl>0；近涨停（≥99.7% up_price）；成为领涨且 pct≥8% 且近日高（≥99.5%）。
- **profile**：v5 = 5 日 / dd 2%；v6 = 3 日 / dd 0.5%（更激进，需前瞻验证）。hard floor 两者均 8%。

## 5. 成交模型（真实，非最坏价）

- 限价 `L = min(open[D] × (1 + 0.5%), basket_price)`；开盘窗口（默认 09:30–09:31）结算后 **fill = min(窗口VWAP, L)**。
- `basket_price` **仅为放弃线**，**MUST NOT** 作为成交假设（旧行为按 basket 记成交=虚构 ~1.9%/笔滑点，已废）。
- 窗口最低价 > L → **SKIP**（`paper_skips.jsonl`，`LIMIT_NOT_REACHED`，**不静默丢弃**）；无窗口数据 → 回退到 L（`fill_fallback`）。
- 唯一实现：`paper_record._fill_price_from_window`。
- **数据源单一性（OHLCV 故意不接公共源 fallback）**：止损/peak-dd 依赖的分钟线 OHLCV **只**来自专有 API（`client.minute_line`）。**MUST NOT** 把公共源（akshare/腾讯等）价格接入 live 止损路径：不同复权/时间戳/坏tick 会算出不同的 peak/dd，使 book B 与验证 next-close 口径及 API 喂的回测**静默漂移**——正是 data_health 要抓的"真的谎言"。OHLCV 不可得时应 **fail-safe（持有/跳过）**，而非用二手数据动作。公共源仅允许用于**带 provenance 标记、经对账的研究/回填工具**，且 book A/B 记账永不读 `source='public'`。

## 6. 仓位与资金

- `deploy_ratio` 默认 **0.5**（留 dry powder）；`max_total_exposure_ratio` 默认 **0.67**；等权滚动现金；整 100 股；单边费率 **1bp**。
- 被 quality-governor 过滤的 slot **留现金、不再分配**（保守）。

## 7. Quality Governor（默认 shadow）

- `primary_score`（按 mode）：起爆→`jssb`；接力→`xcjw + 0.5·max(jsjl,0)`；N字/孕线低吸→`xcjw + 0.6·cjs`；其余低吸→`xcjw + 0.8·cjs`。
- 阈值 `PRIMARY_THRESHOLD = 150`；`primary < 150` → `weak_primary`。`p_score ≤ -2` → `p_tail_warning`（仅警告）。
- 模式：`off`（忽略）/ `shadow`（默认，仅审计 `quality_governor_audit.jsonl`，不拦截）/ `on`（弱 slot 留现金）。唯一实现 `quality_governor.py`。

## 8. Kill-switch（性能型，唯一部署控制）

- 依据 book A 近 5 个出场日累计收益：`< -3%` → book B deploy **减半**；`< -5%` → book B **停买**。
- **传感器常活**：book A 记账与数据采集**永不**因 kill-switch 停止。唯一实现 `paper_record._kill_switch_factor`。
- 指数/regime deploy gate 已回测全败 train+test 一致性（`backtest_deploy_gate.py`），故**不接任何指数 regime gate**；性能 kill-switch 是唯一 deploy 控制。

## 9. 双钥匙资金动作边界（real-capital，借 QuantDinger 双钥匙）

- **paper / sensor / research / simulation 永远放行**（research 永不被资金门阻塞，传感器永不停）。
- **real_capital 必须同时**：
  1. env `XIAOCAO_LIVE_TRADING_ENABLED=true`；
  2. 签名授权 `output/live/live_authorization.json`（HMAC 对 `XIAOCAO_LIVE_SIGNING_KEY` 校验，**agent 无法自签**——签名密钥由人持有，automation 环境不携带；由交互式 `scripts/authorize_live.py` 铸造）。授权**带 scope（max_notional / side / code 白名单）与到期**。
- 任一缺失/签名被篡改（含非 ASCII 签名）/过期/越权/**或越权属性缺省**（如限定 max_notional 却未指定 notional、限定 side/code 却为 None）→ **硬拒**（fail-closed）。
- 审计：real_capital **ALLOW 必须可持久审计**——若审计写失败则转为 DENY（不下不可审计的真实单）；DENY/always-allowed 行为 best-effort（审计永不让交易回路崩溃）。`require_capital_action` 拒绝时**只**抛 `CapitalActionDenied`。
- 唯一实现 `src/xiaocao/live/safety.py`；真实下单 **MUST** 经 `require_capital_action(...)`，仅在 ALLOW 时下单。
- **现状**：尚无 real-capital 调用点（paper-only）；本节是 paper→real 的结构缝，使切换=配置翻转而非重构。

## 10. 异常 / 升级策略（agent 皮层）

- **只上报真实异常**：脚本失败、缺预期输出、`候选股 NONE`、缺 paper-record 输出、对账 MISMATCH、`HARD_STOP` 触发、现金不足、可疑数据。
- **非异常（正常）**：`SELL_DEFERRED`（盘中只诊断）、`T+1_blocked`、非交易日 skip、book A 单独结算。
- EOD 是**盘后审计**，非新多空判断：强调执行纪律、A/B 证据、数据采集健康、账户一致性、未决风险。

## 11. 契约不变量（可执行回归 → `tests/test_operating_contract.py`）

- [x] paper/sensor/research 永远放行；unknown kind 默认拒。
- [x] real_capital 缺任一钥匙 / 签名篡改 / 过期 / 越权 / 超额 → 拒；双钥匙 in-scope → 放行；每个决定入审计。
- [x] `require_capital_action` 拒时抛 `CapitalActionDenied`。
- [x] 成交 ≤ basket 放弃线（`_fill_price_from_window`）；窗口最低价 > L → SKIP。
- [ ] （后续）settle_book_a 只用 next_close 且幂等；decompose_pnl 三项金额求和 = account realized_pnl（容差=取整）。

## 12. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-06-20 | 首版：架构原则 + book A/B 口径 + 成交模型 + 仓位 + governor + kill-switch + **双钥匙资金边界** + 异常策略 + 不变量。 |
