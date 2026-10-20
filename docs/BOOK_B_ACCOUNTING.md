# APP Book B 账本

会计口径以 [Operating Contract §6](OPERATING_CONTRACT.md#6-仓位与资金) 为准。
`src/xiaocao/live/book_b_accounting.py` 是统一入口，使用 Python 标准库 SQLite；
原有成交、资金事实及其校验、账户锁继续复用。paper A/B/T 不在此数据库中。

## 自动消费

早盘预检和完整生命周期投影共享同一自有成交重放，幂等导入已证明事实并保存
账户/估值观测。返回的 `account.accounting` 含确切来源 head、净投入、含费成本、
已实现及浮动盈亏、标记净值和预计退出费用。实际成交费用未齐时
`realized_pnl`、`unrealized_pnl`、`cumulative_pnl` 为 `null`；旧估算仅保留在
`provisional_realized_pnl` / `provisional_unrealized_pnl`。`fee_status` 和
`pending_fee_orders` 逐日期/委托列出待核项。资金差异未分类时总盈亏也为 `null`。
用户 2026-10-01 澄清无需为了精确收益硬平账。严格小于 10 元的完整现金差额，
仅在新鲜完整快照、完整原始账链且无未决计划时，可标为 `cash_discrepancy_tolerated`。
原始观测现金及差额保留，执行现金采用 APP 可用和重放现金的较小者；不造调整
分录、不把差额归为费用/盈利/本金，累计盈亏仍未知。该状态不放行 UNKNOWN、
未证明资金预留、坏账链或缺失应结算日；已批准未入账的资金事项保持独立。
未决 BUY 的现金预留尚未精确证明时标为 `cash_reserve_reconciliation_required`，
不会用重放余额声称现金闭合。较新资金事实存在时，较早快照不得用于当前观测或划拨。
金融分录更新后，旧观测仍供历史核验，当前决策和结算必须重新取得有效观测。

保护性监控的原账户绑定、自有成交、数量、T+1 和市场/订单门仍独立严格验证。
仅 SQLite 存储读写故障可返回 `accounting.status=unavailable`，继续合法自有 SELL；
现金/NAV/累计收益输出为 N/A，BUY 和 EOD 结算继续失败关闭。成交后的风险刷新失败
返回 blocked 风险证据并保留原成交/终态回执。原始证据或等式损坏不走此降级。

EOD 在原交易/对账入口结束后导出一次累计明细。周报读取这份日期绑定的报告，
保留估值时间、待核实际费用和 UNKNOWN/缺失结算，不把观测当成结算。
正式结算还要求 `actual_fees_complete`，现金碰巧闭合不能证明费用已核对。

```bash
CODEX_AUTOMATION_ID=xiaocao-book-b-live-morning PYTHONPATH=src .venv/bin/python scripts/book_b_accounting.py statement
```

`--receipt <exact-path>` 可使用含 `account`/`snapshot` 的已验证不可变凭证；旧格式凭证
仅在 ownership/funding head 仍一致时可导入。命令不调用 APP、不下单，也不补造价格。
输出 `report_path` 与 `details_path`；无当前估值时 headline NAV/盈亏为 N/A。
CSV 每行包含经济事件、账户现金累计余额、成本、净投入变化、盈亏和原证据 hash。
明细另带账户/环境、lot、来源执行事件、单价/金额与确认状态；原生成交 ID 和逐笔
发生时钟未被原证据提供时留空，保留 trade_date 和观察时钟，不伪造对应关系。
报告和 CSV 名称绑定导出 schema 与来源 head，字段扩展不覆盖旧格式导出。
v2 JSON 的 `source_observation` 保留原始观测及其 hash；`valuation` 是明确标注
费用最终性的展示视图，旧估算观测也不会在该视图中输出最终净利润。

## 明细来源与异常

数据库 `entries`/`postings` 保存以分为单位的平衡分录及不可变链，`observations`
保存 hash-bound 估值，`metadata` 绑定策略起点、环境与账户。唯一来源键防重复，
整次导入由原 `account_writer_lock` 与 SQLite 事务保护；中断后重跑导入可恢复。
已导入 JSON/JSONL 事实被删除或改写会阻断，不能静默重建来掩盖变更。

原计划估算率只保留为不可变的历史暂估，不作为最终净利润的依据。
当前原生 port 尚未提供逐笔费用/资金流水采集，
`record-cash --receipt` 只是接收已证明的原生资金流水，不会生成该证明。
额外费用只接受 `additional_non_trade_charge`，避免把总交易佣金重复扣除；
分红要求权益日同账户持仓与自有数量完全匹配，利息期间必须全部在现金政策批准后。
缺证明或混合人工持仓时保持待对账。

`record-trade-fees --receipt <proof>` 接收 `broker_snapshot` 加
`foundersc-native-trade-fees.v1` 的 `statement`，不调用 APP 或生成凭证。
statement 必须有 `source=foundersc_native_app`、已证明的账户绑定、与新鲜完整
snapshot 相同时钟及账户 hash，以及正文的 `receipt_sha256`。以 `event_id` 选中
唯一行；该行带交易日期、`broker_order_id`、代码、方向、股数、`gross_notional`、
按原账链顺序列出的 `ownership_event_hashes`、`coverage=complete_order`、
`fee_basis=broker_final_itemized`、带符号的 `net_cash_change` 和 `fees`。
fees 必须明确给出非负、精确到分的 `commission`、`stamp_duty`、`transfer_fee`、
`other_fee`（确认无费用也要明确为零），净现金须等于带方向成交总额减全部费用。
这是一份实际原生明细的接收协议；自填数字/余额差额不能充当来源证明。
每笔费用由账户+原生事件唯一去重；新更正凭证须用新的 event_id，并以顶层
`replaces_fee_entry_sha256` 精确引用当前费用证明分录。后续漏/新增成交会使旧的
complete_order 证明失效并阻断，不能把旧费用套给新成交。
多委托同时补发现成交时，可用 `{"fee_receipts": [proof1, proof2]}` 一次提交完整
更正；全部 proof 必须引用相同新鲜快照，同一事务校验/追加后再整体重估，任一
失败全部回滚。不会因另一委托尚待更正而留下半笔完成状态。

费用证明和差额均追加到同一 SQLite 账链。买费进入原 lot 成本，卖费减少净收入；
每次 sync/账户观测自动消费已接受证明并重算部分卖出的含费平均成本，最后一笔
消耗剩余分。不重写旧估算分录、历史观测或资本引用的分录前缀。CSV 保留原分录
金额，新增 `actual_fee`、`final_realized_pnl`、`final_cost_change`；未证实则留空。
`gross_pnl` 为未扣费价差，仅供说明成交，不是净利润。差额分录另列，不能将
原分录与新增 final 列再次相加。旧导出不覆盖，新导出使用新的 schema 标识。
可用现金/NAV 的保守提交上限、资金政策、风险单位数、高点/暂停均沿用既有门。
原生资金更正使用 `kind=REVERSAL` 与 `reverses_entry_sha256` 引用一条已证明的
费用/分红/利息分录，金额须严格相反且来源账户一致。同一原分录只能冲正一次，
不能冲正冲正；全部记录保留。后续正确事件仍由原 `record-cash` 入口追加。
此入口不改自有成交、数量或委托证据；缺少原生更正证明保持阻塞。

明确的新资本划拨使用 `allocate --receipt <fresh-full-snapshot> --approval-reference <exact-approval>`。
该入口要求已有相同快照的估值且没有未决 BUY 预留；按明确划拨分类更新原资金链
和单位净值，不改签名授权或重新绑定计划。普通自动化只读政策、消费已证明事实，
不会调用此入口。未分类差额需要先区分成交、费用、收益和资本归属。

## 备份与验收

```bash
CODEX_AUTOMATION_ID=xiaocao-book-b-live-morning PYTHONPATH=src .venv/bin/python scripts/book_b_accounting.py backup --output-dir output/audit/book-b-accounting-backup.sqlite3
```

`--output-dir` 在此动作指定新备份文件。SQLite backup API 取得一致副本，随后执行
integrity_check、分录平衡和完整 hash-chain 校验；既有备份不会被覆盖。恢复需在
原账户单写者停写后，将验证副本恢复为同根目录的 `accounting.sqlite3`，保留相应
原始证据，运行 `sync`、`statement` 核验来源和明细；恢复不重试任何委托。
历史资本基准与首次批准划拨不等于已证明整个 APP 账户的历史银行入金。
