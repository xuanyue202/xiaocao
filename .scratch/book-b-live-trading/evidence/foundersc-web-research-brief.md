# Founder Securities Web App research brief

Status: REQUESTED

Target task: `01a003f6-eb36-7180-910b-f02837410fd0`

## Purpose

为 `.scratch/book-b-live-trading/PRD.md` 选择一个能忠实表达 Book B 订单计划的 Web App 路由。只读调研，不保存、不启动、不下单、不撤单。

## Required evidence

### A. Account and environment binding

- 找到模拟/实盘环境的精确、唯一、可读回标识；记录安全切换方式和切换后回读。
- 找到当前资金账号的脱敏指纹、账户名称或其他可稳定绑定 `logical_account_id=primary` 的字段。
- 证明路由切换、页面刷新、重新打开持久会话后，环境和账户不会被模板猜测。
- 所有 locator 必须限定在精确容器内并验证唯一性；禁止全页泛文本点击。

### B. Route semantics

分别对“盘前集合竞价”“定时单”和可访问的实盘手工限价入口建立字段表：

- route URL and exact form container
- 股票代码、市场、方向、数量、价格、日期、触发时间
- 默认值、单位、最小步长、必填项、校验错误
- 参与比例、浮动价格、触发价格、是否撤单、残单处理的真实语义
- 目标数量是硬上限、目标值还是可能被算法放大的值
- 09:20–09:24 创建后，何时进入券商委托；09:30 后未成部分如何处理
- 是否允许精确表达 `L=min(open*1.005,basket)` 和固定整手数量

不得仅凭表单标签推断语义；优先读取页面说明、风险提示、历史策略详情和已有历史委托。

### C. Receipt and reconciliation

只读定位并记录：

- 活动策略、当日委托、当日成交、持仓、资产、可撤单列表的路由和表结构
- 可见的稳定标识：策略 id、委托号、合同号、证券、方向、价格、数量、已成、未成、状态、时间、失败原因
- 分页、虚拟滚动、刷新按钮、默认日期过滤和数据新鲜度标识
- 策略记录如何一一关联到委托和成交；如果做不到，明确缺口
- 已有历史记录中的状态词全集及其终态/非终态含义，不创造映射

### D. Mixed-account ownership

- 持仓页是否能区分人工与策略来源；不能区分时明确说明。
- 同代码总持仓、可卖数量、当日买入/T+1 字段是否可读。
- 委托/成交页能否依靠策略 id 或备注稳定标记 Book B 归属。

### E. Market safety facts

- 表单或证券详情是否展示权威涨停价、跌停价、停牌/交易状态、最新价和更新时间。
- 若只展示涨跌幅或名称，明确标记“不足以支持 `LIMIT_DOWN_BUY_BLOCKED`”。
- 不调用高频行情接口，不用静态 5%/10%/20% 规则冒充券商事实。

### F. Authentication and confirmation

- 登录态失效时的页面特征。
- 哪些操作会触发登录密码、交易密码、安全控件、风险协议、OTP 或 CAPTCHA。
- 只检查控件是否存在及其前置条件；不输入密码、不点击最终确认。
- 记录取消或关闭未提交表单是否完全无副作用。

### G. Speed and recovery

- 在不提交的前提下，各测 3 次：会话 probe、打开精确表单、填表到可读回状态、打开委托/成交页；给出中位耗时。
- 验证刷新、路由跳转、弹窗关闭、标签页重连后的状态。
- 列出所有会导致 OpenCLI 进入 `UNKNOWN` 的页面行为，以及可用的只读 reconcile 路径。

## Deliverable

把结果写到同目录的 `foundersc-web-capability.md`，结构为：

1. capability matrix
2. exact locator matrix with uniqueness evidence
3. broker status vocabulary
4. reconciliation keys
5. timing measurements
6. risks and unknowns
7. recommended route, or explicit `NO_ROUTE_PROVEN`

每个结论区分 `observed`、`inferred`、`not proven`。不要创建 OpenCLI 生产模板；不要修改当前 PRD。
