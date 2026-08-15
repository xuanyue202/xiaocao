# 方正证券量化平台 Web capability evidence

**取证时间：** 2026-08-15（Asia/Shanghai）
**任务：** `01a003f6-eb36-7180-910b-f02837410fd0`
**范围：** 只读检查模拟/实盘环境、盘前集合竞价、定时单、实盘手工限价、策略/委托/成交/持仓/资产页面，以及公开的一方前端 bundle。
**副作用边界：** 本轮没有输入凭据，没有保存、启动、提交、撤单或下载模板；仅打开页面、读取 DOM/页面说明、打开后取消空表单，并读取现有页面。

## 结论先行

**推荐结果：`NO_ROUTE_PROVEN`。**

已观察到三个候选入口，但没有任何一个同时满足 PRD 的正式 adapter 契约：精确的账户绑定、Book B 价格/数量语义、稳定的策略→委托→成交关联、可证明的残单/撤单回读、权威涨跌停与交易状态事实，以及会话恢复后的 exactly-once 边界。

- **最接近 Book B 即时限价语义：** 实盘手工限价。页面有代码、限价、数量、买/卖，适合作为未来 controlled mock acceptance 的第一候选；本轮没有提交，因此没有提交回执、交易密码前置条件、委托号关联或撤单闭环证据。
- **最接近早盘竞价操作：** 组合算法→盘前集合竞价。字段和页面说明较丰富，但它是带参与比例、浮动价格、触发价格、算法残单策略的目标量算法，不是 Book B 的固定限价即时委托；不能原样表达 `L=min(open*1.005,basket)`。
- **定时单：** 能表达固定代码、方向、价格、数量、日期和时间，但最早下单时间、部分成交、残单和取消语义没有形成可验证的券商回执契约。

本轮关于环境切换的事实修正：上一轮从模拟盘切到实盘是用户主动点击，不是自动化误触，也不作为页面风险事故证据。本轮为用户已允许的只读验证，使用了精确容器内唯一 locator，并在切换前后回读；精确 locator 仍是正式资金 adapter 的工程不变量，因为提交必须绑定唯一环境、账户和动作。

## 1. Capability matrix

| 能力 | observed | inferred | not proven / gate impact |
|---|---|---|---|
| 模拟/实盘绑定 | 页面顶部唯一 `div.switcher___KVAWw` 显示 `模拟盘交易` / `实盘交易`，切换后同一页面正文回读对应反向文案。 | 这是页面环境选择器；可作为 probe 的必要条件。 | 未证明服务端返回了可持久审计的 environment id；未证明刷新、重新接入新持久会话后环境和目标账户仍由同一稳定指纹绑定。 |
| `logical_account_id=primary` | 页面显示的是脱敏后的登录手机号指纹（本文件只记为 `186******455`）；用户已澄清 login 手机号与 trade 资金账号不同但属于同一套账户。 | 用户配置语义上可把两者归属到 `primary`。 | UI 未显示资金账号、账户名称、合同号或稳定账户 fingerprint；无法仅凭页面把本次页面绑定证明为 `primary`，也无法证明 keychain 中 trade account 被哪次请求使用。 |
| 盘前集合竞价字段 | 路由有 09:20–09:24 分钟选项、秒、方向、参与比例、目标数量、浮动价格、限价/触发价、涨跌停标识和是否撤单。 | 这是可配置的竞价算法策略；目标数量不是成交保证。 | 没有创建策略，故没有策略 id、券商委托回执、实际入委托时刻、部分成交和 09:30 后残单事实；无法证明符合 Book B 固定限价公式。 |
| 盘前集合竞价语义 | 一方页面说明/tooltip 指向：参与比例按实时最大市场成交量计算；浮动价格基于实时最优执行价；限价和触发价会影响是否进入执行；是否撤单控制算法结束前未成委托。 | 参与比例、浮动价、触发价都会使实际成交价格/数量受市场与算法影响。 | 说明是前端语义，不是本轮实际券商成交证明；未证明目标量不会超过/少于输入量的全部边界，也未证明 09:30 后残单的最终状态。 |
| 定时单 | 条件单→定时单弹窗有代码、方向、委托价格、委托数量、委托日期、小时/分钟和风险协议；小时含 9、10、11、13、14，选择 9 后分钟可到 30–59。 | 适合表达一次性的固定字段计划。 | 未见重复周期、撤单/残单策略或成交截止时间；tooltip 的“最早下单时间为当前时间 5 分钟后”未通过真实提交验证；没有回执和部分成交证据。 |
| 实盘手工限价 | 实盘只读路由可打开；表单有代码、委托价格、委托数量、限价/市价、买入/卖出；委托页可打开并显示当日委托/成交等 tab。 | 这是三者中最接近“指定价格、指定数量”的入口。 | 未点击买入/卖出；因此没有交易密码/安全控件触发条件、提交回执、委托号、可撤单成功回读或 exactly-once 证明。 |
| 活动策略 | 条件策略和组合算法活动页均能打开；条件策略列表使用 `scroll-load-data`，组合算法右侧有运行概况/委托/成交/日志。 | 列表是虚拟/滚动加载，不应只读取首屏 DOM。 | 当前没有可用的活动策略行，未观察到实际策略 id 与委托/成交关联。 |
| 当日委托/成交 | `myAccount/query` 和手工委托页都有当日委托、当日成交、历史委托、历史成交入口；表头/前端 source 定义了时间、代码、方向、数量、价格、状态、失败原因等字段。 | 可作为 reconcile 的页面来源之一。 | 当前页面无记录；未证明实际历史记录会返回策略来源、策略 id、稳定委托号到成交号的完整链路。 |
| 持仓/资产 | 资产页显示总资产、证券市值、可用资金、可取资金、在途资金和持仓表；实盘持仓表本轮观察到非空行，字段含持仓/可用。 | 可读取账户层面的资金和总持仓事实。 | 没有人工/策略来源字段；没有独立 T+1 字段或当日买入来源；不能安全推导 Book B 自有可卖数量。 |
| 可撤单 | 手工委托页有 `全部撤单`；通用账户查询 source 只有 `x.canWithdraw && !vm.isQuantization` 时才渲染逐行撤单。 | 手工非量化委托可能有撤单入口。 | 没有点击撤单；量化策略路径的可撤单入口/回读未证明，不能把“按钮存在”当作撤单成功。 |
| 市场安全事实 | 页面可显示现价/五档占位字段，表单有涨跌停标识和价格触发设置。 | 这些是交易/算法输入的一部分。 | 未读到权威涨停价、跌停价、停牌/交易状态及其时间戳；不能用涨跌幅或页面名称替代 `LIMIT_DOWN_BUY_BLOCKED` 检查，应按 `LIMIT_DOWN_CHECK_UNAVAILABLE` 失败关闭。 |

## 2. Exact locator matrix with uniqueness evidence

所有交互均限定在精确页面容器内，并在动作前验证 `count=1`；没有使用全页泛 `getByText` 点击。页面中的哈希 class 只作为本轮取证证据，不应直接视为未来模板的稳定 API。

| 页面能力 | 精确容器 | 子 locator / 读取目标 | 唯一性证据 | 只读动作与结果 |
|---|---|---|---|---|
| 环境切换 | `div.switcher___KVAWw` | `getByText("点击切换至实盘", exact=true)`；切换后同容器内 `getByText("点击切换至模拟盘", exact=true)` | 容器 `count=1`；两个方向分别 `count=1` | 仅做环境读回；切到实盘后正文显示 `实盘交易`，反向切回后显示 `模拟盘交易`。 |
| 竞价主表单 | `.pdc-operation` | 页面主 `form` | `.pdc-operation count=1`、主 `form count=1` | 读取必填项、默认值、选项和风险 checkbox；未保存/启动。 |
| 竞价添加证券 | `.pdc-data-option` | `getByText("添加证券", exact=true)` | `.pdc-data-option count=1`；添加链接 `count=1` | 打开空证券弹窗读取字段，随后在同一 `.al-modal-container` 内 `getByRole("button", {name:"取消", exact:true}) count=1` 并取消；弹窗关闭且数据区仍为 `暂无数据`。 |
| 竞价证券弹窗 | `.al-modal-container` | `form input[name="stockCode"]`、数量/参与比例/价格 placeholder 字段 | 弹窗 `count=1`；弹窗内证券代码 input `count=1`、form `count=1` | 只读字段结构和校验属性；未填代码、未确定。 |
| 定时单入口 | `div.new-condition-strategy` | `.new-condition-strategy-dropDown` 内 `getByText("定时单", exact=true)` | 外层 `count=1`；下拉项 `count=1` | 打开创建弹窗；只选小时 9 以读取分钟选项，然后取消。 |
| 定时单弹窗 | `[role="dialog"]` | `input[name="taskName"]`、`input[name="stockCode"]`、`input[name="quantity"]`；`getByRole("button", {name:"取消", exact:true})` | dialog `count=1`；关键 input 各 `count=1`；取消按钮 `count=1` | 三次填写无交易意义的策略名并读回，未填证券/价格/数量，随后取消；dialog 归零，无策略行。 |
| 实盘手工限价 | 页面内 `form` | `form input[placeholder="请输入证券代码"]`、价格、数量；form 内精确 `买入` / `卖出` button | form `count=1`；三类 input 各 `count=1`；买/卖按钮各 `count=1` | 只读表单、五档和持仓；没有点击买入/卖出。未限定 form 时 placeholder locator 曾出现非唯一结果，因此 production 不得省略容器。 |
| 手工委托页 | `a.gs-tab-withdraw` / 委托详情容器 | 当日委托/成交/历史 tab；`a.gs-tab-withdraw` 仅读 DOM | 撤单链接 `count=1`；无行数据 | 读取 `全部撤单` 的 DOM 绑定但未点击；状态为 `全部`、数据为空。 |
| 账户查询 | `.ma-q-table-container` | `.gs-d-entrust-tabs` 内四个精确 tab；资产/查询/日志链接 | 查询容器 `count=1`；四个 tab 在容器内各 `count=1` | 读取 tab、筛选项和表头；没有导出、撤单或修改筛选以外的副作用。 |

## 3. Route and field semantics

### 3.1 盘前集合竞价

**路由（observed）：**

```text
#/home/combAlgorithm
#/home/combAlgorithm/create?type=盘前集合竞价
```

主表单 observed 字段：

| 字段 | observed 默认/约束 | 语义证据 | 结论 |
|---|---|---|---|
| 证券代码 | 添加证券弹窗必填，placeholder `请输入证券代码` | 代码解析后 source 内部带 `marketId`，但页面没有独立市场选择框 | 市场不能作为用户可读、稳定绑定字段证明；`not proven`。 |
| 委托方向 | 买入/卖出 | source 组装 `side` | `observed`，但没有实际委托回执。 |
| 目标数量 | placeholder `请输入目标数量` | tooltip/source 使用 `targetQuantity`，并明确实际成交量会受市场与参与比例影响 | 目标值而非成交保证；是否严格硬上限未证明，不能当作固定成交量。 |
| 参与比例 | placeholder `请输入参与比例的数值`，client validation 为 `0 < value <= 30` | tooltip 说明按实时最大市场成交量计算 | 是算法参与约束，不是固定数量/固定成交时间的替代；服务端边界未证明。 |
| 触发时间 | 小时固定 `09`；分钟 `20..24`；秒必填 | 页面字段和 risk/form source | 可表达 09:20–09:24 的触发配置；何时真正转成券商委托未证明。 |
| 浮动价格 | 主表单/证券行有 `默认为0`；source tooltip 给出股票约 `[-0.1,0.1]`、ETF 约 `[-0.01,0.01]` 的调整范围与步长 | 基于实时最优执行价加减调整 | 会改变实际委托价格，不能当作 Book B 固定限价字段。 |
| 限价 | 可选，`默认为0, 表示不限价` | source 说明买入最优价高于限价或卖出最优价低于限价时不触发，后续行情更新再判断 | 是触发/资格条件，不等同于“按该价立即下单”。 |
| 触发价 | 可选，`默认为0,表示不触发`，方向 `>=` / `<=` | source 说明最优竞价价需满足条件 | 触发器；实际入委托时刻与残单终态未证明。 |
| 涨跌停标识 | `涨停能卖跌停能买` / `涨停不卖跌停不买` | 页面选项和 source `limitAction` | 只是策略选项；未读取权威涨跌停价、交易状态和时间戳。 |
| 是否撤单 | `是` / `否` | tooltip/source 的 `isCancelOverdue`：算法结束前取消未成委托 | 有残单取消意图，但实际部分成交、结束时刻和撤单回执未证明。 |

**固定数量/价格与 PRD 的比对：**

- `L=min(frozen_open*1.005,basket)` 不是原生字段。浮动价引用实时最优执行价，限价/触发价是条件，不存在 `basket_price` 或该公式字段。[observed]
- 可以预计算一个静态价格再填限价的想法属于 adapter 外部推导；本轮没有证明所需的 frozen open、basket、涨跌停和交易状态均来自权威新鲜事实，因此不能作为 production route。[inferred / not proven]
- 目标数量可录入，但 tooltip 说明实际成交量会偏离；固定整手校验只从前端输入 class/validation 痕迹看到，未证明服务端/实际撮合的整手约束。[not proven]
- 09:30 后未成部分：只证明“是否撤单”配置存在，不能证明券商在何时、以何状态、以什么数量结束残单。[not proven]

### 3.2 定时单

**路由与入口（observed）：**

```text
#/home/conditionStrategy/active
```

从精确的 `div.new-condition-strategy` 打开 `定时单` 后出现一次性创建弹窗。字段：

- 策略名称：默认 `定时委托1`，必填。
- 证券代码：必填。
- 委托方向：必填。
- 委托价格：必填，固定价格输入。
- 委托数量：必填，带数量校验 class。
- 委托日期：必填。
- 委托时间：小时选项 `9/10/11/13/14`；选择 9 后分钟出现 `30..59`。
- 风险协议 checkbox，`启动` 和 `取消` 按钮。

一方 bundle 的 tooltip 文本说明最早下单时间为当前时间 5 分钟后。[observed from source] 没有看到周期、有效期、自动撤单或残单处理字段。[observed] 因此它能表达固定价格/数量/日期/时间，但“只提交一次”“部分成交如何结束”“取消和残单如何回读”仍是 `not proven`。

### 3.3 实盘手工限价

**路由形状（observed）：**

```text
#/home/orderByHand/<opaque-account-route>/position
#/home/orderByHand/<opaque-account-route>/entrustDetail
```

`<opaque-account-route>` 是页面运行时的内部数字路由参数，本文件不保存其具体值。实盘 position 页可读到列：`代码/名称`、`市值`、`成本价`、`现价`、`持仓`、`可用`、`盈亏`、`盈亏率`；本轮实盘返回了非空持仓行，但不保存具体金额和数量。

限价 form observed：

- `证券代码`：`请输入证券代码`；
- `委托价格`：`请输入委托价格`，单位显示为元；
- `委托数量`：`请输入委托数量`，单位显示为股；
- `限价 / 市价`、`买入 / 卖出`；
- 五档盘口和 `可用数量` 展示区。

这是最接近 Book B “指定价格、指定数量”的页面入口。[inferred] 但本轮不点击最终买入/卖出，不测试交易密码控件，也不把表单出现当作可提交契约。最小步长、整手校验、服务端拒单语义、委托号和撤单结果均 `not proven`。

## 4. Reconciliation surfaces and keys

### 4.1 Routes and table structures

| 事实 | 路由/入口 | observed fields and behavior |
|---|---|---|
| 资产、持仓 | `#/home/myAccount/assets` | 资产：总资产、证券市值、持仓参考盈亏、可用资金、可取资金、在途资金；持仓：代码/名称、市值、成本价、现价、持仓、可用、盈亏、盈亏率。 |
| 账户查询 | `#/home/myAccount/query` | 策略名称/状态筛选；当日委托、当日成交、历史委托、历史成交；当前无记录。 |
| 账户日志 | `#/home/myAccount/log` | 路由和入口 observed；本轮没有把日志当作成交证明。 |
| 手工委托/成交 | `#/home/orderByHand/<opaque-account-route>/entrustDetail` | 状态筛选 `全部`；当日/历史委托和成交 tab；`下载Excel`、`全部撤单`；无行数据。 source/隐藏表头含时间、代码/名称、买卖、委托量/价、状态、拒单原因、操作，以及成交量、成交价、成交金额。 |
| 条件策略活动 | `#/home/conditionStrategy/active` | 策略名称、代码/名称、策略创建时间、策略类型、状态；列表节点带 `scroll-load-data` 和 `source-strategy-data`，属于滚动/虚拟列表。 |
| 组合算法活动 | `#/home/combAlgorithm` | 类型筛选含 `TWAP_PRO`、`VWAP_PRO`、`POV_PLUS`、`POV_PRO`、`盘前集合竞价`；状态含未启动、待运行、运行中、已停止、手工停止；右侧运行概况/委托/成交/日志，概况列含完成率、目标数量、委托数量、成交数量、成交均价、成交额、委托次数、撤单率。 |
| 策略详情 | source route | `home.algorithmTrade.detail`、`home.conditionStrategy.detail` 均有 `entrustDetail` 和 `log` 子路由；本轮无活动行，未取得实际 id。 |

### 4.2 Stable identifiers, pagination and freshness

- 一方 source 在当日/历史委托和成交导出对象中包含 `orderId`；当前 table 不渲染它，且本轮无记录可回读。[observed]
- 组合算法创建 source 组装策略 `id` 和 ticker 字段；活动列表为空，因此没有实际策略 id 样本。[observed]
- 不能证明策略 id、orderId、成交记录和持仓变更之间有稳定的一一关联；没有观察到共同的 Book/source/intent 字段。[not proven]
- 账户查询 source 在 `totalElements > 200` 时分页，page size 为 200，页数为 `ceil(totalElements / 200)`；历史查询有日期范围校验，最大 30 天，默认约为过去 7 天至昨日。[observed from first-party source]
- 账户查询活动状态有约 3 秒自动刷新 callback；页面没有可依赖的“最后更新时间”字段。[observed from first-party source / page]
- 组合算法 body 使用可滚动数据区；条件策略明确使用 `scroll-load-data`，因此 adapter 不能只读首屏或以 DOM 行数为完整性证明。[observed]

### 4.3 Cancellation and residuals

通用查询 source 只有在 `x.canWithdraw && !vm.isQuantization` 时渲染逐行 `撤单`；`全部撤单` 会收集可撤 id 后再确认并调用撤单服务。本轮没有点击任何撤单控件。[observed]

这形成硬缺口：对 `isQuantization` 的盘前集合竞价/策略委托，没有在本轮证明可撤单路由、撤单成功回执或残单数量回读；不能用“是否撤单”策略字段替代 broker-side cancel receipt。[not proven]

## 5. Broker status vocabulary

以下是页面 source 中的原始状态词/代码全集；本轮没有历史行让状态转换可被实证。除“名称本身”外，不把任何词强行映射为终态。

### 5.1 组合算法/策略状态

| code | label |
|---:|---|
| `0` | 未启动 |
| `4` | 待运行 |
| `1` | 运行中 |
| `2` | 已停止 |
| `3` | 手工停止 |

条件/任务状态 source 还出现：`INIT=未启动`、`RUNNING=运行中`、`STOPPED=已停止`、`STOPPED_MANUAL=手动停止`、`ERROR=内部错误`、`NOTSELECT=未选择`，以及默认 `未运行`。

### 5.2 委托状态

| raw code | raw label |
|---|---|
| `49` | 未报 |
| `50` | 待报 |
| `51` | 正报 |
| `52` | 已报 |
| `53` | 废单 |
| `54` | 部成 |
| `55` | 已成 |
| `56` | 部撤 |
| `57`, `70` | 已撤 |
| `97`, `66` | 待撤 |
| `98` | 未审批 |
| `99` | 审批拒绝 |
| `100` | 未审批即撤销 |
| `65` | 未撤 |
| `67` | 正撤 |
| `68` | 撤认 |
| `69` | 撤废 |

从词面看，`已成`、`废单`、`已撤`、`审批拒绝`等可能是终态，`已报`、`部成`、`待撤`等可能是中间态；这是名称驱动的 `inferred`，不是本轮的生命周期证明。adapter 必须保留 raw code/label，并以实际回读和数量变化决定状态。

## 6. Mixed-account ownership and market safety

### 6.1 Mixed account

- 持仓表只有账户总持仓列，未见人工/策略来源、Book、intent 或策略 id。[observed]
- 同代码的总持仓、可用数量可以显示，但未见独立的当日买入、T+1 冻结原因或自动账本 lot 标识。[observed]
- 不能证明“可用”就是 Book B 可卖数量，也不能把同代码人工持仓安全地排除或归属到 Book B。[not proven]
- 委托/成交页 source 有 `orderId`，但本轮没有实际策略/委托行，也没有稳定 source 标识，无法证明 Book B 归属。[not proven]

### 6.2 Market safety

本轮没有读取到同时具备以下属性的权威事实：涨停价、跌停价、停牌/交易状态、最新价、采集时间戳。手工页面五档在无可用证券时显示占位符；算法表单的涨跌停选项和浮动价格不是行情事实。[observed]

因此不能支持 `LIMIT_DOWN_BUY_BLOCKED` 的正向判断；在正式 adapter 中应按 PRD 采用 `LIMIT_DOWN_CHECK_UNAVAILABLE` 失败关闭，不能用涨跌幅、名称或静态 5%/10%/20%规则替代。[inferred from PRD, not proven by platform]

## 7. Authentication and confirmation

- 先前只读登录页观察到手机/资金账号 tab、`PassGuardCtrl.js`/`pgeCtrl` 安全控件痕迹；普通 DOM `fill()` 不是可靠的密码输入依据。本轮没有再次填密码，也没有读取或输出任何凭据。[observed in prior round]
- 本轮环境只读切换没有弹出密码、OTP、CAPTCHA 或风险确认；这不能证明提交操作也不会触发交易密码。[observed / not proven]
- 盘前集合竞价和定时单都有风险协议 checkbox 以及 `保存`/`启动` 或 `启动`按钮；这些按钮未点击。[observed]
- 实盘手工限价有买入/卖出按钮；未点击，故交易密码、安全控件、二次确认出现的前置条件保持 `not proven`。
- 盘前集合竞价空证券弹窗和定时单弹窗均通过精确 `取消` 关闭；没有新增行、策略或数据。说明“打开—取消”无副作用。[observed]

## 8. Timing and recovery measurements

测量口径：同一已登录持久会话；每次从 `Date.now()` 开始，路由打开后轮询 `document.readyState` 和目标页面文本；不提交、不保存、不撤单。数值是当前会话的路由/DOM ready 时间，不是冷启动网络 SLA。

| probe | run 1 | run 2 | run 3 | median | 判定 |
|---|---:|---:|---:|---:|---|
| 会话 probe：读取唯一环境容器、手机号脱敏指纹、资产/页面就绪 | 27 ms | 18 ms | 17 ms | **18 ms** | `observed`；只表示当前 DOM readback 快，不代表账户服务端 freshness。 |
| 打开盘前集合竞价精确表单：`combAlgorithm/create?type=盘前集合竞价`，读回“参与比例/启动”等字段 | 79 ms | 29 ms | 31 ms | **31 ms** | `observed`；SPA 缓存/已加载资源条件下的 route-level 时间。 |
| 定时单：精确打开、填写无交易意义的策略名、读回 dialog、精确取消 | 1,027 ms | 1,025 ms | 1,026 ms | **1,026 ms** | `observed`；未填代码/价格/数量，取消后 dialog=0。 |
| 打开实盘委托/成交页：从资产路由到 `orderByHand/<opaque>/entrustDetail`，读回当日委托/成交 tab | 52 ms | 53 ms | 51 ms | **52 ms** | `observed`；同一会话、已加载资源，非冷启动。 |

### Recovery observations

- 一次直接路由跳转后页面曾保持 `document.readyState=loading` 且 body 为空；同一标签后续恢复，未执行重复提交、重试订单或撤单。
- dev log 出现重复 Angular 加载 warning，以及一次 `home.orderByHand`→`home.myAccount` transition superseded。另一个空白标签被 Edge 扩展浮层阻止自动化；没有关闭/操作该扩展 UI，也没有建立第二个 OpenCLI session。[observed]
- 恢复路径是：读取同一 tab 的 URL/ready/body → 等待/再次读取 → 只读打开资产、环境、委托/成交和策略页面。页面仍为空、路由回退、环境/账户指纹不一致、目标容器 count 非 1、弹出密码/风险/OTP/CAPTCHA、提交后没有明确回执，均应让 OpenCLI 进入 `UNKNOWN` 或停止 reconcile，而不是重放提交。[inferred safety rule]
- 当前已能用同一标签完成上述只读读回；没有证明新浏览器进程或全新持久会话重连后的稳定性。[not proven]

## 9. Risks and hard gaps

1. **账户 binding 不完整：** 页面只给手机号脱敏指纹，未给资金账号/合同号/稳定 account fingerprint；`login` 与 `trade` 两个配置字段的同逻辑账户归属还不能由页面回读证明。
2. **环境 binding 需要保留：** 本轮环境切换使用容器唯一 locator 并前后回读；先前用户主动切换不构成自动化事故证据，但生产提交仍必须对 environment label/id 做精确读回。
3. **价格规则不匹配：** 盘前集合竞价的浮动价/最优价/触发价/参与比例改变了计划语义，原生没有 `basket_price` 与 `min` 公式。
4. **数量/时序不匹配：** 算法的目标数量可能与实际成交不同；09:20–09:24 只是触发配置，不是已证明的 broker order-entry 时间；09:30 后残单终态未知。
5. **委托和成交关联未闭环：** source 可见 `orderId` 和策略 `id` 的各自存在，但没有实际样本证明两者及成交、持仓能一一关联到 `plan_id`/Book B。
6. **量化撤单未证明：** 通用逐行撤单明确排除 `isQuantization`；算法页没有经过实际残单→撤单→回读的安全验证。
7. **混合账户归属缺失：** 不能区分同代码人工仓与策略仓，也没有已买/T+1/lot 来源字段；自动卖出存在误卖风险。
8. **市场安全事实缺失：** 无权威涨跌停、停牌/交易状态和时间戳；必须 fail closed，不能凭页面涨跌幅或规则推断。
9. **认证和副作用边界未闭合：** 未测试提交，因此交易密码、安全控件、风险协议和“响应丢失后如何读回”的实际条件未知。
10. **页面恢复风险：** loading 空壳、路由 transition 被 supersede、Angular 重复加载 warning、虚拟列表未加载、扩展 UI 阻塞，都会使 OpenCLI 观测不完整；未完成 reconcile 前不能重放任何动作。

## 10. Recommended route

### Formal decision

```text
NO_ROUTE_PROVEN
```

当前不创建生产 OpenCLI 模板，也不把任何候选路由写成 `production adapter`。这不是因为页面没有字段，而是因为 PRD 要求的是“可验证的正式交易契约”，而本轮关键事实仍停留在字段/静态说明或空页面观察层。

### If a later controlled acceptance is separately authorized

后续只建议按以下顺序补证，不改变 Book B 经济规则：

1. 先在模拟环境做唯一账户/环境/字段回读，再用明确允许的最小模拟订单取得一次真实提交回执；不以页面跳转替代回执。
2. 优先验收手工限价的固定价格/数量和 orderId→成交→持仓链路；需要证明空响应、部分成交、撤单歧义和重复调用均不会重复提交。
3. 仅当手工限价无法满足早盘竞价时，单独验收盘前集合竞价的 target/participation/price/cancel 语义；先证明实际委托和残单状态，再决定是否接受它作为 Book B route。
4. 定时单保留为一次性计划候选，必须补齐 effective time、部分成交、残单、取消和策略/委托关联证据。

以上只构成验收顺序，不构成实盘启用、保存策略或创建模板的授权。

## Evidence sources

- 本地要求和验收标准：`../PRD.md`、`foundersc-web-research-brief.md`。
- 方正量化 Web App（已登录页面，取证时使用）：[quant.foundersc.com](https://quant.foundersc.com/qtassets/dist/index.html#/user/login)。
- 一方前端 bundle（路由、状态词、分页/撤单分支和 tooltip/source）：`https://quant.foundersc.com/qtassets/dist/static/app_main.6a232e.js`，2026-08-15 读取。
- 相关可读路由形状：`#/home/myAccount/assets`、`#/home/myAccount/query`、`#/home/myAccount/log`、`#/home/conditionStrategy/active`、`#/home/combAlgorithm`、`#/home/orderByHand/<opaque>/position`、`#/home/orderByHand/<opaque>/entrustDetail`。

## 11. Static bundle supplement (anonymous, no business API)

一份独立的匿名静态审阅补充了前端模块信息。它只读取入口 HTML、公开的一方 JS bundle 和 `PassGuardCtrl.js`，未登录、未携带凭据、未请求 `/qt/...` 业务 API，因此以下仍必须与已登录运行时事实分开。

### 11.1 Stronger static reconciliation evidence

- `todayEntrust`、`historyEntrust`、`todayDeal`、`historyDeal` 支持 `taskId`、状态、日期范围和 `pageNum/pageSize` 等筛选；组合任务 id 会传给 `allEntrust`、`allDeal`、`tradeStatus`、`getLog`。[observed from source]
- 组合任务列表字段含 `id`、`taskName`、`sname`、`status`、`time`、`completionRate`；组合执行明细含 `id`、`taskId`、代码、方向、价格、状态、委托/成交时间与数量、撤单数量/比例、`canWithdraw`、成交率。[observed from source]
- `MyAccount.withdrawEntrust` 使用 `{id: ...}`；组合撤单弹窗收集 `canWithdraw=true` 的明细 id 后才进入确认提交。[observed from source]
- 因此，`taskId` 作为“策略筛选委托/成交”的候选关联键、组合 `id` 到明细查询的代码路径是 `observed`；但本轮没有实际策略行、委托行或成交行来证明服务端回读的一一对应关系，`plan_id`/Book B 归属仍是 `not proven`。

### 11.2 Static route payload details

- 手工限价的静态提交 payload 形状包含 `marketId`、`stockCode`、`side`、`priceType`、`price`、`quantity`；这进一步支持“它是固定价格/数量候选入口”的判断，但不证明服务端接受、成交或返回稳定 receipt。[observed / not proven]
- 定时单的静态字段含 `executeDate`、`executeHour`、`executeMin`、`expiredTime`，价格既可选 `NOW/BUY1..SELL5/HIGHLIMIT/LOWLIMIT/OPEN/PRECLOSE/HIGH/LOW`，也可将具体数值编码为 `type=SPECIFIED` 与 `entrustPrice`。这丰富了字段语义，但没有证明执行次数、有效期到期后的活动委托处理或残单处理。[observed / not proven]
- 盘前集合竞价 source 字段名包括 `entrustQuantity`、`max_percentage`、`triggerTimeMinute`、`triggerTimeSecond`、`limitPrice`、`limitUp`、`isCancelOverdue`、`floatPrice`、`triggerRunningPrice(Direction)`；没有发现 Book B 的 `frozen_open`/`basket_price` 或等价 `min` 公式。[observed]

### 11.3 Static market/authentication evidence

- 行情 source 暴露 `nowPrice`、`preClosePrice`、买卖盘、涨跌幅、`lowLimitPrice`、`highLimitPrice`，并有停牌提示 `stop`。[observed from source]
- 这些字段没有在已登录运行时被本轮以“证券 + 时间戳 + 权威来源”回读，因而不能升级为 `LIMIT_DOWN_BUY_BLOCKED` 所需的事实；仍按 `LIMIT_DOWN_CHECK_UNAVAILABLE` 处理。[not proven]
- 登录/交易 source 包含 `login`、`fundIdLogin`、`fundLogin`、`checkTradePassword2`；安全控件包括 `pge`、`pwdSetSk` 等字段；手工下单和策略启动各有最终确认框，实盘还有风险评测/适当性签署相关接口。[observed from source]
- 这些 source 证明“存在前置检查/最终确认路径”，不证明本次账户的实际触发顺序；本轮没有输入密码、OTP/CAPTCHA，也没有点击提交确认。[not proven]

### 11.4 Static refresh/recovery details

- source 中资产/持仓约 60 秒刷新，委托/成交/策略详情约 3 秒刷新；普通委托/成交 page size 200，组合委托详情 page size 20，组合策略列表 page size 10；手工提交状态约每 300 ms 轮询并在约 33 次后提示“委托提交中，请稍后”。[observed from source]
- 这些刷新/轮询间隔是恢复设计输入，不是“提交成功”证明；写请求响应缺失仍必须进入 `UNKNOWN`，再以当日委托、成交、资产、持仓和任务过滤只读对账，禁止盲重试。[inferred]

**补充后的主结论不变：** `task_id_to_entrust_deal_filter=observed`、`composition_task_id_to_detail/allDeal/tradeStatus=observed`、`withdraw_id_and_canWithdraw=observed`；`account_owner_split`、`T+1_semantics`、`Book_B_exact_price_L`、`server_execution/receipt/cancel_finality` 仍为 `not_proven`，正式推荐仍为 `NO_ROUTE_PROVEN`。
