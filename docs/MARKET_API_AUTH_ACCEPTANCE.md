# 行情登录修复与推荐验收（2026-09-14）

## 故障与修复

当前运行环境未带有效登录 token 时，行业/板块、三个候选池、小草核心指标及
smallGrass 接口返回 990502；同样请求携带有效账号 token 后成功。游客 token
不能替代账号会话。该对照确认了客户端认证缺口，不证明服务端何时变更、是否
发送通知，也不能从网页按钮灰色推断 API 权限。

`a45913a` 接入专用 Keychain 会话；`737c3c3` 补齐账号密码登录和失效恢复。
账号密码仅存 `xiaocao.market-data.credentials`，会话存
`xiaocao.market-data.session`，account 均为 `runtime`。官方
`https://p-xcapi.topxlc.com/user/v2/login` 使用前端一致的字段编码；普通请求
复用会话，990502 后仅对官方 `/stock/` 读取串行重新登录并重试一次。
跨进程锁、已更新 token 复用和 120 秒登录冷却避免并发登录风暴。

显式 `XIAOCAO_API_TOKEN`（包括空值）覆盖 Keychain 并禁用自动登录。
验证码、短信验证、缺凭证或重复拒绝保持认证错误，不转成空候选。
没有假设 refresh-token 接口；账号密码不进入参数列表、日志或仓库。

## 验收层次

| 层次 | 本次证据 | 不能据此推断 |
| --- | --- | --- |
| 认证回归 | 48 项通过，含失败不覆写、一次重试、两进程仅登录一次、凭据隔离 | 服务端永久接受凭证 |
| 登录与核心 API | 真实密码登录、独立进程 7 项核心预检通过 | 全市场来源完整或推荐流程完成 |
| 完整推荐 | 15:38:27–15:40:13，真实重新登录后运行原版 `auto_daily.sh morning-prerecommend`，原进程退出 0 | 09:25 当时的结果、下单或成交 |

完整推荐在独立 detached checkout（`737c3c3`）运行，使用 SQLite 一致性缓存
副本及训练、模型、持仓输入副本。实际网络调用之间增加 0.8 秒间隔，不替换
API 返回值、策略或筛选门槛。共 93 次官方请求全部返回 8200，其中一次登录，
其余 92 次行情请求均带 token。

产出 17 个信号、14 个 active、14 条快照，14 条 K/P 分数均为有限数；二级
筛选 3 个候选，★E 1 个。8 项情报待复核队列 ready，报告和快照的日期、行数、
SHA-256 与冻结 manifest 独立重算一致，`deterministic_status=succeeded`。
没有 unresolved 来源记录，但 populated/8200 本身不证明供应商全市场完整性。
本次没有生成交易账本或 APP 执行产物，持仓副本 hash 未变。

## 辅助告警的准确归属

- 隔离流程报告 `stale_market_cache`：隔离输入未复制
  `output/live/daily_reconstructed.jsonl`。后续只读核对生产文件，最新日期为
  `20260914`，生产 `stale_market_cache` 返回空列表。不能把该测试输入缺口
  报成生产日线桥中断，也不能据此证明每只股票的日线覆盖完整。
- posture 的旧有效期仍在；这是独立判断上下文的时效问题，不自动延长有效期。
- 推荐阶段有 8 项情报待复核是阶段边界，尚未完成后续独立研判或交易执行。

## 后续维护与复验

凭证变更使用本地隐藏输入入口：

```bash
PYTHONPATH=src .venv/bin/python scripts/configure_market_data_auth.py --dialog
```

核心接口只读检查：

```bash
env -u XIAOCAO_API_TOKEN PYTHONPATH=src .venv/bin/python scripts/market_data_preflight.py --date today
```

完整推荐复验必须使用独立目录：保留原版生产脚本、复制必要历史/模型/日线
重建输入、独立缓存和输出，再运行 `bash scripts/auto_daily.sh morning-prerecommend`。
不要在正式 checkout 重跑已冻结的当天生产器。保存原进程退出、报告、信号、
冻结绑定和请求统计，分别核验主流程与辅助健康状态；收盘后测试不得冒充开盘回放。
参见 [测试约定](TESTING.md) 和
[行情运行指引](../.codex/skills/xiaocao-trading/references/market-data.md)。

本机原始验收材料保留在 `output/research/api-auth-20260914/recommend-e2e/`，
不提交账号、行情缓存、模型或运行账本。临时 checkout 清理后，产物保存在
该目录的 `artifacts/`；原始 manifest 中的绝对路径保留为历史来源，不改写其内容。
