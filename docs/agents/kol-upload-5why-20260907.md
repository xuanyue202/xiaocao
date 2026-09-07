# 2026-09-07 local upload: 5 WHY and acceptance

| 对象 | 状态 | 说明 |
|---|---|---|
| [视频] WHY 1：为什么停在上传？ | 实机复现 | 适配器只检查、不挂载文件时也超时。分步执行定位到导航的等待及后续复合页面读取；不能据此倒填历史 11:13 的泛化失败为“已证实未挂载”。 |
| [视频] WHY 2：页面为什么超时？ | 实验定位 | 原上传页同步读取和已完成 Promise 成功，但 100 ms 计时器等待超过 115 s，目录 fetch 同样不能完成。它呈 hidden。前置准确的原窗口后，同一页事件循环、目录接口和上传均恢复。可操作根因是后台上传页未恢复可执行状态；尚未证明 Edge 内部具体是哪一种冻结策略。 |
| [视频] WHY 3：已有 foreground 参数为什么不够？ | 源码证据 | 本机 OpenCLI 1.8.6 / 扩展 1.0.24 的 tabs/select 只执行 tabs.update(active=true)，不前置已有窗口。goto 的已在目标 URL 快路径也不会前置窗口，随后仍进入依赖页面事件循环的等待。 |
| [视频] WHY 4：为什么之前检查显示正常？ | 身份错位 | browser 命令使用 surface=browser；站点适配器使用 surface=adapter。相同 site:baidu-netdisk 名字不等于相同页面。检查页显示空队列；真正的原上传页保留 4 条已成功记录。 |
| [视频] WHY 5：为什么模型只能反复报错？ | 工程缺口 | 目录检查混合导航、广告点击、样式改写、网络和队列读取；异常被压成 browser_command_failed，测试没有后台页事件循环失败和跨 surface 的边界。恢复 SOP 也只写“前置”，没有精确定义和读回。 |
| [视频] 修复 | 可执行流程 | 复用唯一 adapter 页，不重复导航；只检查模式禁止重建页面；按该页实时几何信息和完整 URL 唯一匹配 Edge 窗口并前置一次，再验证事件循环。目录检查移除广告/样式写操作；阶段回执、统一超时和附着后不确定性保留到诊断。上传已开始的新事件清除历史临时错误字段，历史 ledger 不改写。 |
| [视频] 原任务恢复 | 无重复 claim | kol-netdisk-8735ae55a49c3c12：完整云端扫描目标为 0；原队列完整、4 条成功对照、目标 0；输入、回执、目标 UI 均无本次文件。既有 resume_reconciled_failed_upload 记录唯一 repair claim 后提交一次，未放宽任何重传门槛。 |
| [视频] 本地闭环 | Handoff完成 | capture kol-99deca989cbe；live l_6a9d60d7e4b0694c3546c8c0；20260907 盘前大师班直播(9月7日)-compressed.mp4；101320814 bytes，2252.701031 s。11:53:42 +08 upload_started，随后 video_ready；邮箱 created 时间 2026-09-07T03:56:13.802Z。 |
| [视频] 凭据与验收 | 已核对 | media SHA-256 8735ae55a49c3c1218deb8aa0ac86b7042e7477de97b1bcea640e6811444eef4；handoff ID a5b5411356935fb408886e75f8770b104edc9e7e717d3af62f7d5d433625dbe9；mailbox content SHA-256 72d00be158fa1fccfbda9dfbb468103c7cb30e229fc17054a98be0aa508f90fb。capture acceptance 的全部 14 项检查通过。 |
| [视频] 新代码实测 | 已核对 | 固化后的 helper 实际发出 foreground.begin/end、event_loop.begin/end、folder_scan.begin/end；同一目标返回 already_present、exactCountBefore=1、uploaded=false，原队列保留 5 条成功记录。没有为测试再上传。 |
| [视频] 完成边界 | 尚非全部完成 | 本节点完成下载、上传和权威邮箱 Handoff；远端分析、发布等业务完成只能看同一 ID/hash 的 ack，不能从本地测试推断。 |

执行标准位于
[上传 SOP](../../.codex/skills/kol-intelligence/references/opencli-baidu-netdisk-upload.md)。
冻结页可能暂停任务队列的背景说明来自
[Chrome Page Lifecycle 文档](https://developer.chrome.com/docs/web-platform/page-lifecycle-api)；
本次因果判断以以上同页对照实验为准，不把通用文档当作本机内部状态的证明。
