# Book B 正式交易模块 PRD

Status: IMPLEMENTING_GUARDED_SEAM

- Confirmed by: user
- Confirmed at: 2026-08-15
- Scope: Book B real-capital execution through the Founder Securities Web App
- Current behavior: paper-only; this document does not activate or authorize live trading
- Implementation gate: user authorized implementation on 2026-08-15; real-capital
  activation remains separately gated and is not implied by this status.

## 1. Outcome

把当前 Book B 模拟交易的确定性决策原样接到券商界面：Web App 优先，OpenCLI 作为常规执行器；Codex 只在模板异常时接管同一笔操作，先安全收口，再修复并升级模板。

正式交易不引入第二套选股、定价、仓位或卖出规则。券商成交、委托和持仓回读取代模拟成交估算，成为真实资金事实源。

## 2. Confirmed business contract

### 2.1 Books and authority

- 只有 Book B 获得正式交易能力。
- Book A 继续作为传感器；Book T 继续 paper-only。
- 冻结的确定性 ★E 是买入决策源。
- `shadow_only` review 必须继续生成，但 `authority=0`，与下单并行，不得等待、重排、否决或修改正式交易。
- 若未来要把 review 升为 hard veto / `on`，属于新的策略合同，必须另行设计和人工确认。

### 2.2 Capital basis

- 正式 Book B 初始已结算净资产为 `¥30,000`。
- 盈利在结算后增加后续可用净资产基数；亏损在结算后降低基数。
- 未实现浮盈不提前扩大下一批预算。
- 完整沿用当前 Book B 分配器：每日新批次预算上限为已结算净资产的 `50%`，总敞口上限为已结算净资产的 `100%`，同时受可用现金、100 股整手、当前模式资格、槽位和现有集中度规则约束。
- 不增加任何 live-only 仓位、单票、涨跌幅或主观风控阈值。

### 2.3 Buy timing and price

- 当日冻结完成且确定性 ★E 与手数计划已确定后立即准备并提交，不等待 09:31 模拟成交估价，也不等待 shadow review。
- 初始委托限价保持当前规则：`L = min(frozen_open × 1.005, basket_price)`。
- `basket_price` 仍只是放弃线，不是委托价或成交假设。
- 真实成交价、成交量和费用只认券商成交回读；不得用 paper VWAP、basket 或页面跳转补造真实成交。
- 09:30 开盘后必须复核委托、成交和剩余数量。初始委托未成或部分成交时，可在 09:45 前按当前规则处理剩余数量：只有可用实时价 `<= basket_price` 且其他确定性市场安全检查通过，才允许补单；否则停止追价并记录原因。
- 任一状态不明时先对账，禁止盲重试。

### 2.4 New deterministic buy guard

以下规则同时属于 paper 与未来 live 的确定性脊柱；实现时必须先补齐 paper/live parity：

- 当前可信行情或券商事实表明股票处于跌停时，禁止买入，原因码 `LIMIT_DOWN_BUY_BLOCKED`。
- 无法取得新鲜、权威的跌停价/交易状态时，失败关闭，原因码 `LIMIT_DOWN_CHECK_UNAVAILABLE`。
- 不用 `open_pct_change`、名称推断或静态百分比近似替代权威跌停事实。
- 不新增“普通下跌多少就不买”的主观规则。

### 2.5 Sells

- 完整沿用当前 Book B `live_monitor` 的确定性退出、T+1、14:55 和流动性规则。
- 自动卖出只允许卖 Book B 自己经券商成交回读并归属到自动账本的剩余数量。
- 不得把账户中的同代码手工持仓一起卖出。

### 2.6 Mixed broker account

- 正式交易运行在用户现有混合账户中，允许人工交易与自动交易共存。
- 买入前若券商账户已持有候选股票、但该数量不属于 Book B 自动账本，则本次自动买入整笔跳过。
- 每次提交前必须绑定唯一逻辑账户、实盘/模拟环境、证券代码、方向、数量、价格和交易日。
- 登录手机号与交易资金账号可以不同，但必须绑定同一个逻辑账户 `primary`。

### 2.7 Authorization and user involvement

- 长期总开关是用户的持续运行授权，但不能绕过现有 real-capital 双钥匙门、账户绑定和可持久审计。
- 设计、模拟盘验收和 shadow 演练不构成实盘启用。
- 第一笔真实资金订单前仍需用户单独完成最终启用确认。
- 运行中只在不可替代的人类环节打扰用户：登录、OTP、CAPTCHA、券商强制确认，或多次对账后仍无法消除的委托歧义。

### 2.8 Incident notification and takeover

- 交易异常必须通过企业微信发送一次持久、幂等的问题通知，至少包含：账户别名、环境、Book、intent id、买卖方向、代码/名称、委托价、basket、计划数量、已成交数量、剩余数量、当前券商状态、已完成的安全检查、拟执行的下一步和是否需要用户介入。
- 状态已明确时：通知后 Codex 可以接管同一 intent 的安全收口。
- 状态有歧义时：通知并停止任何新提交；只允许继续读回和对账，直到用户或券商事实解除歧义。
- Codex 接管不得重新选股、改价规则、扩大数量或创造新 intent。
- 当前 intent 终态后才能修复 OpenCLI 模板；新模板必须先过模拟回归，不能在一笔未决订单中热切换。

## 3. Deep module design

### 3.1 External seam

正式交易对调用方只暴露一个深模块：

```python
receipt = BookBLiveExecution.execute(plan)
```

`execute(plan)` 必须是可恢复、幂等的完整接口：第一次调用推进订单；进程崩溃、OpenCLI 超时或 Codex 接管后，以同一不可变 `plan_id` 再调用时，先读取持久状态和券商事实，只推进尚未被证明完成的下一步。

调用方不需要知道 DOM 选择器、页面路由、弹窗、交易密码控件、重试次数或券商状态文案。这些都留在模块实现内。

### 3.2 Immutable plan

`TradePlan` 至少绑定：

- `plan_id` / canonical hash
- `strategy_run_id` / frozen snapshot reference / strategy git SHA
- `trade_date`, `book=B`, `logical_account_id`
- `environment=mock|live`
- `code`, `name`, `side`, `shares`
- `initial_limit_price`, `basket_price`, `price_rule`
- `created_at`, `submit_not_before`, `recovery_deadline=09:45`
- Book B owned-lot references for SELL
- expected broker route capability, but not DOM selectors

同一 `plan_id` 的经济字段不可变。需要改变代码、方向、数量或价格时，旧 plan 必须先达到明确终态，再产生新的、关联 `supersedes` 的 plan。

### 3.3 Internal broker seam

模块内部定义 broker port，由两个 adapter 满足：

- production adapter: Founder Securities Web App through versioned OpenCLI templates
- test adapter: in-memory deterministic broker

生产 adapter 内部按四类模板分离：

1. `probe`：只读确认浏览器会话、登录态、环境、账户指纹、页面能力。
2. `prepare`：精确打开唯一表单、填入参数、读回所有字段；不得保存、启动或提交。
3. `submit`：只有 durable claim、精确账户/环境/参数回读、唯一可用提交控件全部成立时，允许恰好一次外部提交。
4. `reconcile`：从策略、当日委托、当日成交、持仓和可撤单列表读取券商事实；绝不因查询失败自动重发。

OpenCLI 模板是 adapter 的实现，不成为策略调用方需要学习的接口。

### 3.4 Durable state machine

建议状态：

```text
PLANNED -> VALIDATED -> CLAIMED -> SUBMITTED
                                 |-> ACKNOWLEDGED -> PARTIAL -> FILLED
                                 |                 |-> CANCELLED
                                 |                 |-> REJECTED
                                 |-> UNKNOWN -> RECONCILING -> terminal or UNKNOWN
PLANNED/VALIDATED -> SKIPPED
```

不变量：

- `CLAIMED` 必须先于任何可能产生券商副作用的点击。
- claim 后超时或响应丢失进入 `UNKNOWN`；此状态只能 reconcile，不能 submit。
- partial retry 只针对券商已证明的剩余数量，且旧活动委托已成交、拒绝或撤单确认。
- 每个状态转换写 append-only event，并带前序 hash、模板版本、页面/账户证明摘要和无凭据的回执。
- 一个逻辑账户同一时刻只有一个 identity-bound writer。

### 3.5 Takeover capsule

模板异常时模块生成凭据安全的 takeover capsule：

- immutable plan and hash
- last durable state and claim
- broker facts already observed
- exact unknowns
- only safe next actions
- forbidden actions, especially duplicate submit
- OpenCLI template version and failure category

Codex 只消费 capsule 完成当前 intent；完成后基于同一故障证据修复模板并在模拟 adapter / 模拟盘回归。

## 4. Founder Web App route requirements

候选路由按“是否忠实表达 TradePlan”选择，不按页面名称偏好：

- 组合算法 → 盘前集合竞价
- 条件单 → 定时单
- 实盘手工限价单（若真实账户开放且可安全模板化）

路由只有同时满足以下条件才能成为 production adapter：

- 精确价格和数量语义可证明；参与比例、浮动价格、触发价或自动撤单不会偷偷改变计划。
- 提交后能得到稳定的策略/委托标识，并能关联到当日委托、成交和剩余数量。
- 可区分模拟/实盘和目标资金账号。
- 可对活动委托完成撤单回读；无法证明撤单成功时不能补发替代单。
- 所有关键页面能处理分页、虚拟列表、刷新和会话恢复。

若没有任何 Web 路由能精确表达即时限价/竞价语义，模块必须拒绝该路径；不能为了“自动化成功”改变 Book B 经济规则。Mac App adapter 留到 Web 方案被证明不可行后再单独设计和验收。

## 5. Morning runtime

```text
09:20 writer starts and probes session/account
      |
dated freeze ready -> build immutable plans -> deterministic guards
      |                                      |
      |                                      +-> skip + audit
      v
submit as soon as plan is ready; shadow review continues independently
      |
09:30+ reconcile broker orders/fills/positions
      |
unfilled/partial -> current price and basket guard -> reconcile/cancel/retry remaining
      |
09:45 terminal cutoff -> filled / partial / skipped / rejected / unresolved
```

09:45 是恢复和补单截止，不是等待开始时间。达到截止后不得继续新增 BUY 风险；未决活动委托必须按已验证的券商能力处理并保留明确状态。

## 6. Evidence and acceptance gates

实现阶段必须依次通过，不能跳级：

1. Paper parity: 当前 Book B 规则不变，并加入 `LIMIT_DOWN_BUY_BLOCKED` / unavailable fail-closed 测试。
2. In-memory broker: crash after claim, lost response, duplicate invocation, partial fill, cancel ambiguity, reject, session loss, mixed manual holding and 09:45 cutoff all pass through the public interface.
3. Founder mock Web App: exact account/environment/field binding, one-submit proof, receipt mapping and recovery tests pass。
4. Shadow production read-only: 用实盘账户只读核对资产、持仓、委托和成交，不产生订单。
5. Controlled mock acceptance: 经用户另行允许后，用明确的模拟订单验收真实页面副作用和 exactly-once 回读。
6. Real activation: 用户完成最终 live enable；首笔仍受双钥匙和 `¥30,000` 初始 Book B 资金边界。

## 7. Current research handoff

Task `01a003f6-eb36-7180-910b-f02837410fd0` 已确认：

- “组合算法 → 盘前集合竞价”有目标数量、限价、触发时间、参与比例等字段。
- “条件单 → 定时单”有代码、方向、委托价格、数量、日期和时间。
- 当前模拟盘“手工下单”路由会退回账户页。
- 调研期间的一次模拟/实盘切换由用户主动操作，不属于自动化误触，也不能作为页面风险证据。
- 生产模板仍必须使用页面容器内的精确唯一 locator；这是正式资金操作的接口不变量，而非从上述用户操作推导出的故障结论。
- 登录安全控件不能用普通 DOM `fill()` 作为可靠依据；首选持久会话手工登录，凭据不进入模板、日志或仓库。

尚缺的 production 证据见 `evidence/foundersc-web-research-brief.md`；在这些证据完成前不选择正式路由。

## 8. Implementation boundary (current increment)

- Xiaocao owns the broker-neutral Book B execution seam, immutable plan,
  append-only state/claim ledger, reconciliation-only UNKNOWN handling, the
  09:45 basket-bounded retry policy, mixed-account ownership guards, proved-fill
  ownership evidence, canonical mode-switch allocation proof, account-level
  writer fencing, durable takeover capsule, and retryable incident outbox. The
  ownership evidence file is deliberately not `positions.jsonl` or
  `paper_trades.jsonl`; those remain the canonical paper account writer.
- The Founder task owns only the versioned OpenCLI source templates and their
  read-only probe/prepare/reconcile/recover contract.  Its current
  `submit_capability=false` is consumed as `NO_ROUTE_PROVEN`; no submit command
  is invoked.
- The existing `auto_daily.sh` paper writer remains unchanged until a proven
  broker route, account binding, receipt mapping, and a separate user-approved
  activation pass exist.
- SELL plans are accepted only when a current Book-B `live_monitor` decision
  explicitly authorizes a supported exit reason, binds an owned lot, and proves
  no T+1 or liquidity block. Ordinary frozen rows cannot become SELL plans.
- BUY plans are sized/validated by the existing `mode_switch.plan_board_lot_orders`
  allocator using rolling settled NAV; `¥30,000` is only the initial mock basis.

## 9. Explicit non-goals for this implementation increment

- 同步更新 Operating Contract/skill references to describe this non-runtime,
  no-submit seam; this does not authorize real capital.
- 不改 Codex Automation。
- 不提交、保存、启动、撤销任何模拟或真实券商订单。
- 不启用 real-capital keys。
- 不设计 Mac App adapter。
