# APP Book B 账本

会计口径以 [Operating Contract §6](OPERATING_CONTRACT.md#6-仓位与资金) 为准。
`src/xiaocao/live/book_b_accounting.py` 是统一入口，使用 Python 标准库 SQLite；
原有成交、资金事实及其校验、账户锁继续复用。paper A/B/T 不在此数据库中。

## 自动消费

早盘预检和完整生命周期投影共享同一自有成交重放，幂等导入已证明事实并保存
账户/估值观测。返回的 `account.accounting` 含确切来源 head、净投入、含费成本、
已实现及浮动盈亏、标记净值和预计退出费用。资金差异未分类时总盈亏为 `null`。
金融分录更新后，旧观测仍供历史核验，当前决策和结算必须重新取得有效观测。

EOD 在原交易/对账入口结束后导出一次累计明细。周报读取这份日期绑定的报告，
保留估值时间、费用估算和 UNKNOWN/缺失结算，不把观测当成结算。

```bash
CODEX_AUTOMATION_ID=xiaocao-book-b-live-morning PYTHONPATH=src .venv/bin/python scripts/book_b_accounting.py statement
```

`--receipt <exact-path>` 可使用含 `account`/`snapshot` 的已验证不可变凭证；旧格式凭证
仅在 ownership/funding head 仍一致时可导入。命令不调用 APP、不下单，也不补造价格。
输出 `report_path` 与 `details_path`；无当前估值时 headline NAV/盈亏为 N/A。
CSV 每行包含经济事件、账户现金累计余额、成本、净投入变化、盈亏和原证据 hash。

## 明细来源与异常

数据库 `entries`/`postings` 保存以分为单位的平衡分录及不可变链，`observations`
保存 hash-bound 估值，`metadata` 绑定策略起点、环境与账户。唯一来源键防重复，
整次导入由原 `account_writer_lock` 与 SQLite 事务保护；中断后重跑导入可恢复。
已导入 JSON/JSONL 事实被删除或改写会阻断，不能静默重建来掩盖变更。

手续费默认沿用原计划估算率。当前原生 port 尚未提供资金流水采集，
`record-cash --receipt` 只是接收已证明的原生资金流水，不会生成该证明。
额外费用只接受 `additional_non_trade_charge`，避免把总交易佣金重复扣除；
分红要求权益日同账户持仓与自有数量完全匹配，利息期间必须全部在现金政策批准后。
缺证明或混合人工持仓时保持待对账。

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
