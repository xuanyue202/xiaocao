# KOL 状态收敛修复：2026-09-08

Status: validation in progress

## 第一性原理

内容类型、来源关系、外部动作、发布完成是四个独立事实。PDF 已取得不代表
视频已取得；需要核对视频不代表 PDF 尚未下载；点击不代表提供方接受；
handoff/邮箱创建也不代表报告、提醒资格、Book 和 ACK 完成。

持久化语义产物可以缓存内容判断，不能永久缓存异步依赖的运行状态。
每个等待必须来自具体对象/版本的真实回执期限，状态改变时重新评估依赖；
不改变原始内容，不伪造完整来源，不重放已有外部效果。

## 5 Why：PDF 为什么无限等主视频

1. 文件确实是已取得的 PDF，但语义路由判为视频摘要伴生件。
2. 伴生件的缓存 bundle 写有 `primary_source_status=pending`。
3. 每轮复用 bundle，没有把它与主视频当前 claim/receipt 关联。
4. 主视频已出现有界失败，PDF 仍刷新自己的轮询期限与 resolved_at。
5. 语义快照与运行状态未分离，测试只覆盖初次 pending，未覆盖依赖转换和重放。

修复：精确 provider identity/version + path/name/size/mtime 关联运行身份；
校验 claim 的来源/版本；复用真实 deadline，保持相同关系幂等；主来源完成
或精确对账失败时重新请求关系判断，保留原 PDF 分析并走既有 fallback/合并路由。
缺失或歧义绑定是 Agent 修复，不制造 provider wait。

## 5 Why：门禁为什么漏掉原 writer

1. helper 返回 pass，但 14:30 的原任务仍在处理盘前视频。
2. `thread/list` 未列出预览为空的任务。
3. 新版 scheduler 初始输入是 `codex_app.automation_update` 输出，普通用户首条消息为空。
4. 旧门禁同时假设列表可见、preview 与首轮 userMessage 必须带 Automation ID。
5. 控制面升级后，测试仍只有旧格式；UI 可见性被误当成运行权可见性。

修复：只读本地索引补充空预览候选，仍经同一 app-server exact readback；
初始 scheduler 输出必须绑定 session id/cwd/source/thread_source，且早于 Agent
工具调用；缺失 scheduler 身份 fail closed。保持原有 task_complete 终态栅栏。
实机恢复验证识别原任务 `01a07fb6-b7e9-7293-aed9-e9f7656a916d` 并返回 peer/no_op。

## 5 Why：为什么出现含糊“需要授权”

1. 点击次数达到有界重试门，状态被投影为外部效果不确定。
2. 文案把 native click attempts 写成“两次确认转存”。
3. 又把一次明确请求允许的额外恢复写成泛化“代理接管授权”。
4. 没有区分用户批准范围、百度接受结果、真实账户登录权限。
5. 文案未直接绑定 provider_outcome、attempt maximum 与 recovery consumed。

修复：去掉已确认的误报，显式输出次数上限/提供方结果/恢复是否已用完；
状态说明不再暗示缺百度权限。用户本次要求只授权同一旧对象一次第三次点击；
2026-09-08 17:02:46 已使用，提供方请求/响应均未观察到，17:32:46 只读对账。

## 今日 handoff 的核验时间线

- 什么都没变：13:14 创建，14:33 尝试，15:19:58 ACK；报告 published，Book no_trade。
- 国家队成本线：13:15 创建，15:20 尝试，15:56:31 ACK；报告 published，Book no_trade。
- 9月8日盘前大师班：13:29 创建；原任务完成转录和语义证据绑定修复；
  原 owner 回报 17:12:29 ACK，报告 published、提醒 delivered、Book no_trade。
- 两篇文章错误的 report_only 判定另交原 owner 原位修复提醒资格；不重发报告/Book/ACK。

## 回归与外部边界

真实旧门禁 fixture 先 red（pass 而非 no_op），修复后 green；PDF 重放 fixture
先 red（idempotent_replay=false），修复后 green。新增依赖完成/失败、版本不符、
固定 deadline 和运行入口不得复用 stale bundle 的覆盖。完整 scoped suite 305 通过。
另修复测试假阳性：四位十六进制测试验证码可能随机出现在 SHA 中，改为非十六进制样本。

不修改交易、账户、订阅范围、收件人、时间表；不下载视频；不创建新 writer。
代码回归通过不等于百度转存成功，也不等于已经证明长期稳定。
