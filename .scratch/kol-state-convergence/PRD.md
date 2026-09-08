# KOL 状态收敛修复：2026-09-08

Status: repaired and validated; old video transfer remains unavailable

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
- 两篇文章错误的 report_only 判定由原 owner 原位修复提醒资格：17:33:34 / 17:33:45
  CAS 更新；Chen 和 FeiFei 均有独立 delivered 回执，重放新增送达为 0。
  原报告 URL、Book、知识和 ACK 保持不变。

## 5 Why：文章为何已发布却漏提醒

1. 来源包含当前方向与触发判断，但提醒资格被判为 report_only。
2. 分析把观点延续、未独立核验、标的未映射和 Book no_trade 混成不提醒理由。
3. 同一草稿同时承载内容价值、事实核验、Book 和提醒判断，边界未独立验证。
4. canonical acceptance 只检查 no_alert_reason 非空，未核对来源绑定的当前性。
5. 测试验证发布与送达机制，却没有覆盖该语义降级反例。

修复 6d8612c：新 extraction request 声明 kol-alert-qualification-v1，要求对
actionable_signals / market_outlook 引用的每条 claim 独立审查当前性和提醒依据。
存在 current claim 时必须 alert_eligible；事实核验、置信度、标的映射和 Book
不参与降级。保留合法历史、失效、方法论、纯确认等 report_only 路由。旧请求兼容。
真实 red→green 覆盖当前方向不得 report_only、缺审查 fail closed、纯确认合法，
以及 unverified + low confidence + market conflict + no_trade 仍可提醒。

## 回归与外部边界

真实旧门禁 fixture 先 red（pass 而非 no_op），修复后 green；PDF 重放 fixture
先 red（idempotent_replay=false），修复后 green。新增依赖完成/失败、版本不符、
固定 deadline 和运行入口不得复用 stale bundle 的覆盖。完整 scoped suite 305 通过。
另修复测试假阳性：四位十六进制测试验证码可能随机出现在 SHA 中，改为非十六进制样本。

不修改交易、账户、订阅范围、收件人、时间表；不下载视频；不创建新 writer。
代码回归通过不等于百度转存成功，也不等于已经证明长期稳定。

### 同链路复核补充

发现通用 absence reconciliation 会把 attempt maximum 提升为 attempts+1，
可能在明确第三次恢复已使用后重新放开第四次。真实回归先 red（4 != 3）；
修复使 consumed operator recovery 在空结果对账后保持 blocked、maximum=3，
读取事实不产生新的操作授权。该边界不依赖调用者记住另行停手。

## 最终实物与回执验收

- 9月7日视频：第三次点击 17:02:46，保留真实 17:32:46 回执等待窗口。
  17:33:57 只读核对目标目录和稳定后的全局精确搜索均无匹配；无提供方请求/响应
  观察，也无视频副本/逐字稿。claim 保持 blocked、3/3、recovery consumed，
  不自动产生第四次授权。此结果不等于提供方明确拒绝，转存根因尚不能据此确认。
- PDF：原语义 owner 只修改 episode_relationship 和 quality_review.limitations[2]；
  主任务验证其余 JSON 完全相同、引文确实存在于 PDF，保留原输入和旧产物副本。
  原 resume-source-wait 进程消费新 canonical bundle 后退出 0；17:50:59 报告 published，
  17:51 Book no_trade、提醒 all_recipients delivered、知识 reusable_knowledge，waiting_count=0。
  报告 ID kr_n46ojlymhaaf7ut7dfvrkl67rsgptzpnsttr7vbr2moudntm2oyq；云端 exact readback
  验证 published + alert_eligible=true 与同一 PDF evidence/source version。
- 最终合并验证：350 项 Python 测试通过，14 项 Node peer-gate 测试通过。
  scoped 命令：pytest tests/test_kol_pdf_dependency.py tests/test_kol_lv_subscription.py
  tests/test_kol_subscription_video.py tests/test_kol_semantic_bundle.py tests/test_kol_daily.py；
  node --test tests/codex_peer_gate.test.js。
- 修复代码已推送：0bfc0bb、801eff5、b0f62bf、6d8612c。保留原交易/知识/test WIP。
