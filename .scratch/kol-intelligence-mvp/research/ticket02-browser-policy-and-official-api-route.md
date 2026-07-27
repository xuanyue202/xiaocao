# Ticket 02：Browser policy 与百度网盘官方 API 路线复核

**核验日期：** 2026-07-20
**范围：** Codex Chrome 的站点权限层、macOS SIP 相关性、百度网盘官方 MCP/Open API 对现有视频文稿的读取能力。只使用 OpenAI、Apple、百度及 `baidu-netdisk` 官方仓库的一手资料；未调用需要用户凭证的接口。

## 结论

1. `claimTab` 成功后仍无法读取 `pan.baidu.com` DOM，不是 Chrome 连接、登录态或 macOS SIP 问题。用户已在 `Settings > Computer Use > Google Chrome > Manage` 将 `pan.baidu.com` 加入 Allowed；fresh `openTabs` 和 `claimTab` 成功，但第一次 `domSnapshot()` 仍返回 `Browser use is not permitted on https://pan.baidu.com/disk/main`。
2. Codex Chrome 有两层权限：用户站点 allowlist/blocklist，以及 Browser Use 的 agent 站点状态。官方文档确认用户站点权限位置；本机随应用发布的 Browser Use 客户端会查询 `/backend-api/aura/site_status` 并在 `feature_status.agent === false` 时拒绝动作。用户 allowlist 不能覆盖该 agent gate。
3. SIP 保护系统目录、系统进程和低层代码注入；它不决定某个普通 HTTPS 域名是否可由已连接的 Chrome 扩展读取。关闭 SIP 既无证据支持，也不是本任务的解决方案。
4. Ticket 02 应从消费者页面 DOM 主路径切到百度网盘官方 MCP/Open API 主路径。官方 `baidu-netdisk/mcp` 的 `file_video_list` 和 `file_meta` 输出包含 `content`：文档内容、视频字幕或音频文稿，若未生产则为空。这是最贴近“717 文稿已经生成，不要重做”的只读入口。
5. 若 `content` 对目标视频为空，第二路径是官方 MediaInsight：个人网盘 OAuth `access_token` + 视频 `fsid` 创建离线转写/AI 纪要任务，轮询后取得逐字稿 JSON/SRT。它不依赖 DOM，但可能重新生成转写。
6. 真实 PoC 的主要未知量不是 SIP，而是 OAuth 与目录授权：新应用的部分基础文件 API 被限制在 `/apps/{appname}`。应先用官方个人限时体验授权调用 `file_video_list`/`file_meta`，验证能否读取现有 `/课程/自己的课/小草`；不应预先搬文件或重做转写。

## 1. Codex Chrome 的两层权限

OpenAI 的 Chrome 扩展文档说明，域名 allowlist/blocklist 位于：

`ChatGPT Settings > Computer Use > Google Chrome > Manage`

允许一个域名表示 ChatGPT 不必再次询问用户；Chrome 扩展本身仍受 ChatGPT 的确认、设置和策略控制。官方故障排查也把“确认目标不在 blocklist”列为第一步。
来源：[OpenAI Chrome extension — Control website access](https://developers.openai.com/codex/app/chrome-extension)

本机应用版本 `26.715.31925` 的 Browser Use 客户端对外部网址调用 `https://chatgpt.com/backend-api/aura/site_status`，并以 `feature_status.agent` 决定是否阻止 agent。2026-07-20 的真实复测中：

- Chrome 能发现目标标签页；
- `claimTab` 成功；
- 用户 allowlist 已包含 `pan.baidu.com`；
- 第一次 DOM snapshot 仍被同一站点策略拒绝。

因此，当前错误不是“用户尚未同意站点访问”，而是更高一层的 agent gate。启用 full CDP access 也不是合法修复；OpenAI 将它定位为开发者调试能力，且本次拒绝明确禁止用 raw CDP 或其他 browser surface 绕过。
来源：[OpenAI Browser — Developer mode](https://developers.openai.com/codex/app/browser)

## 2. SIP 为什么无关

Apple 对 SIP 的定义是保护系统目录、阻止附加到受保护系统进程、约束低层代码注入和未授权系统扩展。它不是浏览器按域名授权系统。当前 Chrome 扩展已经建立连接并成功 claim 普通 Chrome 标签页，也与 SIP 失败的表现不符。
来源：[Apple System Integrity Protection Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/System_Integrity_Protection_Guide/Introduction/Introduction.html)、[Apple Runtime Protections](https://developer.apple.com/library/archive/documentation/Security/Conceptual/System_Integrity_Protection_Guide/RuntimeProtections/RuntimeProtections.html)

## 3. 首选：官方百度网盘 MCP 读取已有 `content`

百度网盘官方 GitHub 组织发布的 MCP Server 声明：

- `file_video_list(dir, page)` 返回视频 `fsid`、path、md5、size、filename、`content`、abstract；
- `file_meta(fsids)` 可按最多 10 个 `fsid` 批量读取同样字段；
- `content` 定义为“文件分段内容，如文档内容、视频字幕、音频文稿，若未生产返回空”。

这意味着 Ticket 02 可以先按精确目录和 basename 找到 717 视频，再只读其 `content`。如果不为空，应把它作为已有云端文稿候选，做长度、时序/分段、开中尾覆盖和视频身份校验，而不是重新请求生成。
来源：[baidu-netdisk/mcp 官方仓库](https://github.com/baidu-netdisk/mcp)

官方仓库提供两种接入：

- 远程 SSE：`https://mcp-pan.baidu.com/sse?access_token=...`；
- Python stdio：主要用于需要本地文件读取的上传场景。

本任务是只读视频元数据和文稿，SSE 能力足够。为了避免 token 进入仓库、日志或 URL 配置，生产实现应通过本机密钥存储注入短期 token，业务 ledger 只保存脱敏的授权来源、目标 `fsid` 和响应内容哈希。

## 4. 第二路径：MediaInsight `fsid` 转写/纪要

百度网盘当前官方文档为 toC 接口提供 OAuth `access_token`，并允许以个人网盘视频 `fsid` 或外部 `media_url` 创建离线音视频转写任务。完成后可取得逐字稿 JSON 和 SRT；逐字稿分段包含角色、开始时间、结束时间和正文。AI 纪要使用同组 MediaInsight 任务接口，可返回全文总结、课程摘要、分段知识点和金融信息等模块。
来源：[百度网盘离线音视频转写](https://pan.baidu.com/union/doc/ai创作能力/音视频理解/离线音视频转写/)、[百度网盘 AI 纪要](https://pan.baidu.com/union/doc/ai创作能力/音视频理解/ai-纪要/)

这修正了旧研究中“公开 API 只能接受外部 URL”的结论。但对 717 来说，它是 fallback：若 MCP `content` 已有现成文稿，不应先创建新任务。

与客户端“笔记 TAB”效果一致的 AI 视频笔记 API 也存在，但官方要求 APaaS `appid + spacetoken` 和商务下发权益，不适合作为当前个人 OAuth PoC 的默认路径。
来源：[提交 AI 视频笔记任务](https://pan.baidu.com/union/doc/ai创作能力/ai笔记/提交-ai-视频笔记任务/)、[查询 AI 视频笔记任务](https://pan.baidu.com/union/doc/ai创作能力/ai笔记/查询-ai-视频笔记任务/)

## 5. OAuth 与目录边界

百度网盘官方 MCP 仓库给个人用户提供限时体验授权：用户在 `openapi.baidu.com` 确认 `basic,netdisk` scope 后取得 Access Token；正式生产则应申请开发者应用。官方授权页面明确请求“访问基础资料”以及“在百度网盘创建文件夹并读写数据”。
来源：[百度网盘 MCP 使用准备](https://github.com/baidu-netdisk/mcp#使用准备)、[百度 OAuth 授权页](https://openapi.baidu.com/oauth/2.0/authorize?client_id=QHOuRXiepJBMjtk0esLhrPoNlQyYd0mF&redirect_uri=oob&response_type=token&scope=basic%2Cnetdisk)

最新开放平台规则对新应用的部分文件 API 设置 `/apps/{appname}` 授权目录边界；MediaInsight 是否能直接处理现有 `/课程/...` 的 `fsid`，文档没有给出豁免结论。因此 PoC 顺序必须是：

1. OAuth；
2. `user_info` 验证 token，但不记录账号信息；
3. 对精确目录调用 `file_video_list`；
4. 对精确 717 `fsid` 调用 `file_meta`；
5. 仅当 `content` 为空且权限允许时，再评估 MediaInsight；
6. 只有接口明确返回目录无权限，才让用户把一条真实视频复制到 `/apps/{appname}` 做隔离 PoC。

来源：[百度网盘创建应用](https://pan.baidu.com/union/doc/使用入门/创建应用/)、[百度网盘权限与配额](https://pan.baidu.com/union/doc/使用入门/权限与配额/)

## 推荐决策

将 Ticket 02 的 provider/evidence 合同从 `baidu_consumer_page + DOM export chain` 改为：

```text
baidu_netdisk_official_api
  -> OAuth liveness
  -> exact directory + basename + fsid identity
  -> existing MCP content when present
  -> MediaInsight fsid fallback only when content is absent
  -> immutable raw response hash
  -> deterministic transcript validation
  -> household reminder
  -> Book KOL-US or explicit no-trade reason
```

保留 DOM 拒绝事件作为能力审计，不再重试、切 CDP 或关闭 SIP。该路线仍严格位于 Ticket 02；不引入直播捕获、订阅、批处理或调度。
