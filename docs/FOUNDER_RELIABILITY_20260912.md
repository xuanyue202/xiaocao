# 方正 APP Python 链路验证（2026-09-12）

本次范围包括 native 客户端、构建缓存、Keychain、适配器、执行日志与归属账本、早盘/恢复/盘中/EOD 入口，以及 Swift 表单读取。APP 为 Operating Contract §1a 中的服务端仿真。测试没有修改策略、仓位参数或自动化时刻，也没有增加早盘前必须运行的测试门禁。

## 可复用的离线验证

```bash
PYTHONPATH=src .venv/bin/python scripts/test_foundersc_reliability.py
```

测试依赖在 `pyproject.toml` 的 `test` extra 中；覆盖率工具只用于开发。入口不会访问 APP、Keychain、行情 API 或生产账本。结果写入 `output/research/foundersc_reliability/`，包含 JSON 和逐行 HTML 报告。

本次该入口 **578 passed，6.07 秒**。计量范围为 10 个 Python 核心模块和 4 个入口脚本；同时运行两组实际编译生产 Swift 函数的行为测试。Python 行覆盖约 **85.5%**、分支覆盖约 **72.8%**，综合约 **82%**。没有新增 coverage 排除项。覆盖率说明触达范围，不证明所有 APP 状态都正确。

全仓库离线回归：`PYTHONPATH=src .venv/bin/python -m pytest -q -m 'not e2e' --tb=short`，**3141 passed，12 deselected，34.50 秒**。排除的是调用行情 API 的 e2e；APP 仿真验证单独执行，见下文。

## 复现并修复的问题

| 问题 | 错误后果 | 修复与验证 |
| --- | --- | --- |
| Swift `Decimal(string:)` 接受有效数字前缀 | `10.00garbage` 可被当作 10.00 | 整串格式验证；编译生产数字读取函数验证合法/畸形价格 |
| Python 委托参数先 `int()` / 六位格式化 | 100.5 股被截为 100，过高精度价格被静默取整 | 启动 helper 前验证有限正值、整股、可无损表达价格与订单身份；异常输入零 helper 调用 |
| 当日与历史部分成交撤单被覆盖为 PARTIAL | 已撤余量再次进入活动订单流程 | 保留已撤终态及成交数量/金额；未知状态也不因有成交而变成已知活动状态 |
| 执行日志跳过损坏 JSON | 重启可能把损坏提交记录当作不存在 | 读取和追加均明确报 `EXECUTION_HISTORY_CORRUPT`；保留原文件，零追加委托 |
| 账户快照与能力检查使用不同资金口径 | 当日买卖后快照有效，下一次委托仍被拦截 | 共用资产等式，要求对应成交方向证据；余额、可用和可取约束保留 |
| Python OCR 分隔符直接去除 | 畸形 `12,34.56` 被改成 1234.56 | 验证完整千分位分组；保留已观察的小数逗号和中欧美式合法格式 |
| 适配器接受的小数逗号在账本投影再次被拒绝 | 合法持仓价、成交价/量在 EOD 报错 | 原始 APP 单元格沿用适配器解析；本地账本与金额仍使用严格 Decimal 规则 |
| 查询忽略非字典行、截取分数行数 | 不完整表格可能被认作完整快照 | 完整验证行类型和整数行数；异常表格只能有界重读 |

集成测试使用真实 Python adapter、TradingExecution、文件事件存储和归属账本，仅替换 native 服务。覆盖提交成功后丢响应、撤单成功后丢响应且暂时无法查询、进程重建后对账、终态重复调用、部分成交/完整成交归属只记一次、BUY→SELL、可卖数量/T+1、错误账户、锁屏和权限缺失。测试服务每笔委托现在生成不同订单号，避免固定假订单号掩盖多订单流程。

## 本周失败与回归对应

| 已保存证据 | 判断 | 对应验证 |
| --- | --- | --- |
| 09-07 opening/sparse：`LIVE_ACCOUNT_SNAPSHOT_BALANCE_EXCEEDS_AVAILABLE`，3 次读取耗尽 | 当日成交现金口径；已有快照修复，本次发现能力检查仍未同步 | `test_foundersc_native_broker.py` 同日买卖资金与 probe 用例 |
| 09-08、09-11 morning：`LIVE_PREPARE_ONLY_NOT_PROVEN` | 表单清空后异步行情回填；原计划未提交 | `test_native_prepare_clear_behavior.py`，本次 APP prepare 再次观察到一次价格回填并成功清空 |
| 09-08 EOD：`LIVE_BOOK_B_BROKER_PRICE_INVALID` | 用小数逗号复现同一错误；原回执缺原始单元格，不能确认历史因果 | `test_native_locale_numbers_survive_account_projection` 覆盖价格、持仓量、成交量 |
| 09-10 optional review：NaN 序列化失败 | 数据准备问题，非 AX 点击失败；已有修复 | `test_book_b_live_policy.py` 缺值和 rendezvous 路径 |
| 09-11 opening/sparse：`LIVE_BOOK_B_OPEN_EXECUTION_RECONCILE_REQUIRED` | 未提交 BUY 阻塞 monitor，已有同 owner 恢复修复 | `test_book_b_live_lifecycle.py` 未声明 BUY、读取后 claim 变化、UNKNOWN SELL |
| 09-07～09-09 closing：窗口未开；09-09 opening：checkpoint 已有 owner | 分别是时间条件与并发所有权保护，不能按故障删掉 | 窗口边界、重叠 checkpoint、CLI 保留当前 owner 的最新回执 |

本周原始证据仍保留在 `output/live/book_b_live_execution/runs/`（含 `archive/`、`repairs/`），没有改写失败记录。

## APP 服务端仿真结果

手动工程试单脚本：`scripts/foundersc_app_rehearsal.py --help`。它使用固定 100 股、显式限价、独立测试目录和现有授权，保存基线、不可覆盖的 intent、提交/撤单 claim 及对账结果。它不代表策略候选或晨间仓位分配，也不进入生产策略账本。

本次 run ID：`ax-20260912-buy-512010-035`；BUY `512010.XSHG`，100 股，0.35。APP 接受订单 **6000002**；精确撤单及当日委托/成交/持仓读取确认 **已撤、成交 0、余量 100、active=false**。前后可用、余额、可取均为 **53522.06**，5 笔持仓不变，成交表为空；保留一笔已撤委托历史。

证据目录：`output/research/foundersc_app_rehearsal/ax-20260912-buy-512010-035/`。`baseline.json` 是原始基线，`events.jsonl` 保留单次提交与单次撤单 claim，`*-after.json` 是 APP 账户回读。重复运行应使用同一 run ID，查看其持久状态；有未知副作用时使用 `reconcile`。`prepare` 在执行已经开始后被拒绝。终态再次调用不会新增订单或撤单。

普通表单清空保留既有 3 秒轮询预算，稳定空值使用短间隔重复读取；本次确实观察到“空→价格回填→重新清空”。3 秒不是完整流程 SLA：登录、多个表格捕获、准备、提交和撤单对账包含多个 APP 动作。现有服务端试单验证了非交易时段受理/撤销；交易时段的撮合、排队、真实部分成交和整段 09:25–09:30 吞吐尚不能由此证明。这些状态以故障注入覆盖，仍需时段内持续观察。

## 全库测试失败的第一性原理复核

初次全库回归的 12 项 KOL 失败在本次修改前 `a2dc0f9` 的独立 Git archive 中同样复现（12 failed、1 passed）。对照日志：`output/research/ax_robustness_20260912/pre-change-kol-tests.log`。因此不是此次方正代码导致，但仍有需要修复的问题：

- 两份原始证据 SHA-256 与登记值一致；2026-08-20 的 `size` 应为 992 字节、2026-08-24 应为 75766 字节。只纠正元数据，没有改动原文或观点，也没有触发发布。
- 固定 2026-07-26 时点的回放测试扫描了持续增长的生产 distill 和本机绝对路径，后来出现的未署名资料、后续观点也进入了旧回放。改成固定日期范围、相对路径及合成证据；后来的官方账号身份样例单独选择。
- 删除依赖未来数据的“至少 4 条过期观点”断言；继续验证观点关联、归属、覆盖、证据和不触发通知/Book 回放。生产中的未知作者检查保留，不把转发的未署名材料归给吕晓彤。
- 新增 UTF-8 字节数、内容改变、无效 hash、缺文件时可移植元数据的行为测试。没有跳过失败测试或放松生产证据校验。

完成后的测试日志位于 `output/research/ax_robustness_20260912/`。剩余未覆盖行/分支可在 HTML 报告逐条查看；优先继续覆盖新出现的业务故障，不能把覆盖率数字本身当成交易正确性的证明。
