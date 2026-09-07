# Hourly Local Native Capture Stages

Read this reference completely at the native launch, identity-resolution,
activation, or continuation/acceptance stage routed by
[hourly-local-capture.md](hourly-local-capture.md), including resumed jobs.
Keep the existing capture/job and process; the local entry owns discovery,
process lifetime, and mailbox completion.

**微信执行标准：只执行下文动作表，不临场分解或探索 UI。**
“打开课程”“输入口令”“关闭课程窗口”必须落到对应行的
前置画面、工具调用和结果检查。未列出的画面/操作停在原任务做离线诊断，
不得以自修复为由试点、重开、刷新或增加快捷键。此约束旨在减少微信敏感操作，
不代表已证明之前退出的具体触发原因，也不保证微信绝不会退出。

## Readiness and launch

Before every native activation prompt, the driver restores and checks the
existing capture's singleton sniffer; a historical armed receipt is not current
process health. Verify/apply the bounded capture PAC only after that health check.
Local capture commands preserve inherited PATH precedence and append installed
Homebrew CLI directories for ffmpeg/ffprobe and transfer helpers.

For `#小程序://鹅直播/<token>`, retain contact/time/token, arm the candidate
baseline, then open the original message once. Skip H5 resolution. Bind the
observed candidate ID, app ID, live ID and post-arm time before downloading.
For H5 entries, retain the process for credential-free identity resolution;
H5 is not playback proof.

For an HTTPS share entry, the default launch route is the verified merchant
Web Link, not chat-window screenshots or a browser player. Run the emitted
`launch_resolver_command` with `PYTHONPATH=src`. The read-only
`scripts/kol_xiaoetong_launch.py` follows the first-party share redirect,
validates the app/live anchor, obtains the provider's public Web Link
representation, ignores the page's mock branch and verifies that the real
`weixin://dl/business/?t=...` ticket embeds that exact replay. The mobile
User-Agent requests the provider's link representation instead of its desktop
QR; it is not login or entitlement. Do not invent tickets, app IDs or page
paths.

Use the returned page URL for identity resolution only. After the same task is
armed and `/proxy.pac` is healthy and applied, execute `launch_command` once via
normal macOS URL handling. If the target mini-program is already open, reuse it.
Regenerate the merchant ticket only for that one activation; never reuse an old
ticket from a report. Read the Goose Live window, not the unshareable main chat
window. Once the exact course is visible, do not resolve again, refresh, or open
a second Scheme. Prefer accessibility controls; when the mini-program exposes
only a window, use the fresh screenshot to click its visible controls. Never
reuse coordinates from an earlier screenshot/run or click the main chat window.
At the visible course-password input, enter `666` once, read it back, and confirm.
Confirmation may automatically start playback. Once the exact finite replay
has been captured, close that course window using the File menu's observed
`关闭全部标签页` (`performClose:`), then verify Goose Live is absent from the
Window menu. If it does not auto-start, click the visible Play control once.
Do not press Space, pause, or mute: keyboard focus is unreliable. Closing the
course window leaves the independent download running; it does not prove the
file is complete. Keep WeChat itself running.
No hooks, WeChat re-signing, hidden
debugging, CDP/DOM evaluation, or protection changes are allowed. If the resolver
cannot prove a ticket, use the original visible message entry. Native
`#小程序://...` tokens still use that original-message fallback, not guessed URL
conversion. A launch plan is not playback, download or upload acceptance.

## Identity, activation, and download

The capture candidate API uses `view=capture`: fresh observed IDs/times only,
without historical title enrichment or remote metadata requests. General display
lists enrich asynchronously with an incremental cache; they cannot bind a source.

1. `resolve_xiaoetong_page`: resolve the supplied `source_url` only to obtain
   and validate the bound Xiaoetong app/live anchor. Accept only a bound H5 live
   page (`/vN/course/alive/l_*`) or MP wrapper resolving to that same live ID.
   H5 is identity-only: return `page_state=unknown`; never log in, inspect a
   player, obtain media, or treat an H5 page state as capture evidence. Retain
   only `app_id`, `pro_id`, `type`, `alive_mode`, stripping share IDs. Accept
   `/v2` to `/v4` rotation only for the same app/live ID.
2. Let the runner arm the exact source job using that stable identity. Do not
   arm another job when switching from the archived H5 route.
3. `activate_xiaoetong_mini_program`: the Agent owns the native WeChat UI
   action; never ask the user to open or select the replay. Use the reviewed
   Computer Use exception (`cua_repl`) against visible WeChat, inspect fresh
   state, keep one foreground session, and read state back after each semantic
   action. Do not use guessed coordinates, hooks, injection, webhooks, storage/cookie
   reads, credential extraction, clipboard loops, CDP/DOM evaluation, or
   rapid/global-shortcut retries. There is no evidence for a magic safe
   interval: wait only for a visible state/sniffer event, and make at most one
   activation attempt per scheduled boundary. If WeChat visibly requires phone
   login, SMS/OTP, CAPTCHA, consent, or shows an explicit protection screen,
   return `wechat_client_login_required` and stop; that is the only
   user-action boundary. At the exact visible course, enter `666` only at a
   visible course-password gate. After auto-play (or one visible Play click) and
   exact finite-media observation, close the course window using W7–W10 below.
   Read back its absence from the Window menu. No continuous playback is required. Return
   `playback_surface=wechat_mini_program`, the exact `source_identity` and
   `live_id`, plus `media_request_observed=true` only when the singleton
   `wx_channels_download` sniffer saw the target request. A current-live
   `liveplay` request alone is not a finite replay; prefer the matching VOD
   `playlist_eof.m3u8` from the mini-program lookback path. Never return signed
   URLs, cookies, keys, or request headers.
4. The source job accepts only the newly observed candidate bound to the exact
   `live_id` and finite playlist. The runner then starts the same
   `type=live_capture`, `compress=true` task and validates the resulting
   `-compressed.mp4`. An H5 identity anchor can never be reported as download
   success.

## 实操 SOP：打开小鹅通小程序 → 下载视频

商户唤起、课程口令、完整回放下载和压缩沿用已验证路径。
2026-09-07 用户将收尾改为关闭课程窗口；当天已实测菜单关闭及窗口消失读回。
空格受焦点影响失效，已废弃；右上角坐标点击曾被工具拒绝，也不作为关闭路径。
只替换本段前端采集操作，步骤 6 起沿用既有上传/Handoff 流程。

1. **保留原任务，先准备抓取。** 从当前 runner 请求/manifest 取出
   `identity`、`capture_job_id`、`source_job_id` 和预期 `source_identity/live_id`，
   不复制本次示例的 ID。已有 PTY 就留在该 PTY；已退出才按 local entry 的
   `capture-xiaocao-item --source-identity <identity>` 续原条目，不再跑全量
   `capture-local`。若已经 `downloading` 或 `cloud_handoff`，跳过小程序操作。
   让 runner 恢复同一 singleton sniffer 并持久化 baseline；不要手动新建下载任务。

2. **唤起前确认媒体流量能被捕获。** 检查 `http://127.0.0.1:2022/api/status`
   和 `http://127.0.0.1:2023/proxy.pac` 健康。执行下面的只读检查，确定当前网络
   接口对应的服务，不把本次的 Wi-Fi 当作所有机器的固定值：

   ```bash
   route -n get default
   networksetup -listnetworkserviceorder
   networksetup -getautoproxyurl "<当前网络服务>"
   ```

   仅在该任务抓取服务健康、已 armed，而当前服务尚未应用抓取 PAC 时执行：

   ```bash
   networksetup -setautoproxyurl "<当前网络服务>" http://127.0.0.1:2023/proxy.pac
   networksetup -setautoproxystate "<当前网络服务>" on
   networksetup -getautoproxyurl "<当前网络服务>"
   ```

   必须读回精确 URL 和 `Enabled: Yes`。PAC 只代理 Xiaoetong，微信安全域名
   DIRECT；其他代理设置不动。没有 PAC 时可能能播放却抓不到，不是登录失败。

3. **一次正常唤起，再输入课程口令。** 对 HTTPS 分享入口，运行当前请求给出的
   `launch_resolver_command`；其命令形态为：

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/kol_xiaoetong_launch.py \
     --source-url '<当前 source_url>' \
     --expected-identity '<当前 source_identity>'
   ```

   核对返回的 app/live ID，只执行返回的 `launch_command` 一次，经正常 macOS
   URL handling 打开商户签发的 `weixin://dl/business/?t=...`。不要把输出里的
   H5 地址打开成网页播放器，不沿用旧 ticket；目标课程已打开时不再唤起。
   `#小程序://鹅直播/...` 入口则用原始可见消息一次，不运行 HTTPS resolver。

   接着严格执行以下动作表 W0–W5，不能把它重新概括成“完成登录/打开播放器”。
   只认**鹅直播课程窗口**中的预期场次标题；主聊天窗口白屏不代表退出。
   本表针对已验证的商户唤起后课程画面；原始消息入口仅在当前画面已有唯一匹配
   卡片时点该卡片一次，然后进入 W1。没有该卡片时不搜索聊天、不滚动试找、
   不猜入口；保留任务做入口诊断。

   **目标参数的取得规则（不是操作策略选择）：** 每次点击前，使用最近一次
   `getAXStateAndScreenshot()` 的结果。若目标有唯一 AX 控件索引，参数就是该
   索引；否则只能取截图中下表所指**唯一可见控件的中心点** `[x, y]`。不得用
   历史坐标、屏幕比例或另一个窗口的位置。表中的 `passwordButton`、
   `passwordInput`、`confirmButton`、`playButton` 均按此规则绑定为索引或坐标，
   不是字符串选择器。目标不唯一、被遮挡或无法定位，停止输入，不能点附近试探。
   菜单参数 `fileMenu`、`closeCourse`、`windowMenu`、`gooseWindow` 只能绑定
   最近 AX 读回中的唯一索引；不得使用坐标或历史索引。

   若当前是微信主聊天窗口，但本任务课程已打开：点击 AX `窗口` 菜单并读回，
   唯一 `鹅直播` 项存在时点击该项并读回课程标题，然后进入 W1。
   不以主聊天窗口可见推断课程已关闭。菜单没有该项且同一场有限媒体已捕获时，
   记录已关闭，跳过重复关闭；用菜单已暴露的 `Cancel` secondary action 收起菜单。

   | 步骤 | 必须已看到的前置画面 | 唯一允许的调用（`cua_repl`） | 结果与下一步 |
   |---|---|---|---|
   | W0 | 一次商户唤起已执行；尚未取得 app 对象 | `var wechat = await cua.getApp("com.tencent.xinWeChat");`；首次调用仅此一行 | 已有该对象就跳过，不重复初始化；进入 W1 |
   | W1 | 已取得 app 对象 | `await wechat.getAXStateAndScreenshot();` | 目标课程且有“输入密码”→W2；口令弹窗已打开且输入为空→W3；已起播或同一场有限媒体已捕获→W7；无口令门且有可见 Play→W6；其他→停止输入 |
   | W2 | 目标课程，唯一可见“输入密码”按钮，无弹窗 | `await wechat.click(passwordButton); await wechat.getAXStateAndScreenshot();` | 必须出现课程口令弹窗和空输入框→W3；没出现不再点 |
   | W3 | 课程口令弹窗内空输入框可见 | `await wechat.click(passwordInput); await wechat.getAXStateAndScreenshot();` | 同一输入框已聚焦/可见输入光标→W4；未确认聚焦不输入 |
   | W4 | 同一空输入框已聚焦 | `await wechat.typeText("666"); await wechat.getAXStateAndScreenshot();` | 必须读回输入值为 666→W5；其他值不清空、不补写、不提交 |
   | W5 | 课程口令框显示 666，唯一“确定”按钮可见 | `await wechat.click(confirmButton); await wechat.getAXStateAndScreenshot();` | 已起播→立即 W7；未起播且有可见 Play→W6；错误/仍为口令门→停止输入，不能再提交 |

4. **抓到后关闭课程窗口：W6–W10。** W5 起播后立即只读同一 source job /
   `view=capture` 候选，确认 baseline 之后同一 app/live 的有限 VOD 已被抓取。
   已有该证据就跳过查询，直接 W7。不要等完整下载才关窗；下载由独立服务继续。
   看见画面不等于文件下载完成；步骤5仍须验收同一压缩文件。

   | 步骤 | 必须已看到的前置画面 | 唯一允许的调用（`cua_repl`） | 结果与下一步 |
   |---|---|---|---|
   | W6 | 同一目标课程未自动起播，明确可见 Play，尚未点过播放 | `await wechat.click(playButton); await wechat.getAXStateAndScreenshot();` | 已起播→立即 W7；否则停止输入，不再点播放 |
   | W7 | 当前 AX 窗口为鹅直播，截图标题为目标课程；同一场有限媒体已捕获 | `await wechat.click(fileMenu); await wechat.getAXState();` | 必须有可用 `关闭全部标签页`，ID 为 `performClose:`→W8；不匹配则停止输入 |
   | W8 | 上一步目标课程的文件菜单仍打开，唯一 `关闭全部标签页` 可用 | `await wechat.click(closeCourse); await wechat.getAXStateAndScreenshot();` | 鹅直播课程消失，回到微信窗口→W9；本轮关闭只提交一次 |
   | W9 | 已回到微信窗口，窗口菜单唯一可见 | `await wechat.click(windowMenu); await wechat.getAXState();` | 列表无 `鹅直播`→W10；仍有该窗口则关闭未证实，不重复关闭 |
   | W10 | 窗口菜单已读回无鹅直播，并暴露 `Cancel` secondary action | `await wechat.performSecondaryAction(windowMenu, "Cancel"); await wechat.getAXState();` | 记录 `playback_window_closed=true`，进入步骤5 |

   `关闭全部标签页` 必须来自已核对标题的鹅直播窗口，不能来自微信聊天窗口
   或浏览器。此处的 `performClose:` 关闭该课程窗口。不要点微信主窗口关闭按钮，
   不使用退出微信、进程终止、全局快捷键或右上角坐标作为替代。

   **本轮输入上限：** 商户唤起一次；有课程口令门时按钮/输入框/确定各点击一次、
   `typeText("666")` 一次；未自动起播才增加 Play 点击一次；课程关闭提交一次。
   这是上限而非配额，已满足的步骤必须跳过。允许的微信工具动作仅为表内
   `getApp`、`getAXState`、`getAXStateAndScreenshot`、目标 `click`、`typeText("666")`、
   菜单 `performSecondaryAction(..., "Cancel")`；不能用 Space、静音、双击、Enter、Tab、Esc、全局快捷键、刷新、
   返回、窗口调整、退出/重启微信、重新打开 Scheme、DOM/CDP 或注入来代替。

   **非预期结果的固定处理：** 调用超时、被拒绝、用户切换窗口或画面不匹配时，
   不重复该输入；只再读取一次当前状态，记录步骤号、实际画面、最后一次调用和
   是否已发送，保留原任务做离线诊断。登录/手机确认/验证码/保护画面不属于课程
   口令门。无法证明课程关闭就如实报告“课程窗口关闭未证实”，不回填成功。
   仅切到微信主窗口、最小化或工具点击成功都不能证明鹅直播窗口已关闭。

5. **确认有限回放，交回原 PTY，等压缩文件完成。** 复用 W7 前已读取的
   `/api/elive/live/candidates?all=1&view=capture`：候选必须是 baseline 之后出现、
   与当前 app/live ID 一致的有限 VOD `playlist_eof.m3u8`，不能选同时出现的
   `liveplay` FLV/M3U8。只读必要的 ID/时间/类型，不输出签名 URL、headers 或 cookies。

   向原 PTY 回一行当前请求指定的 JSON，原样保留动作和身份字段；只在实际读回
   后填写 `playback_surface=wechat_mini_program`、
   `page_state=mini_program_media_observed`、`activated=true`、
   `media_request_observed=true`、`playback_window_closed=true`，并据实填 `password_used`。
   不再要求或伪造 `playback_paused`；新规则只认课程窗口关闭读回。
   原始小程序消息入口还要回同一新候选的 `candidate_id`；不伪造成功字段。

   runner 用同一 `source_job_id` 创建绑定的下载任务。通过
   `/api/elive/source-jobs/<source_job_id>` 取得对应 `task_id`，只跟踪
   `/api/task/list?page_size=500` 中该任务的状态和进度；不要再操作播放器。
   要求 `type=live_capture`、`compress=true`、`compress_inline=true`，并等到
   压缩结束，而不是拿到媒体地址或看到进度就结束。最终以同一任务的
   `media_validated` 回执验收：`-compressed.mp4` 存在，bytes 非零、ffprobe 时长
   与候选匹配、SHA-256 已记录，未保留 raw 副本。保留 PTY，让既有后续流程接手。

   本次实证：capture `kol-3ffdb59330e5`、task `JhgYHS-g4C9DAvFl5RxAq`，
   产物 `20260906 大师班专场(晚18：00开播)-compressed.mp4`，382641026 bytes，
   3345.534247 秒；仅供对照，不是下次运行的参数或整个 Handoff 的成功证明。

6. **Stay through upload and Handoff.** Keep the PTY open while it downloads and
   compresses, validates the MP4, cleans the sniffer/PAC, and uploads. Follow any
   Browser recovery through the existing upload job and persistent session.
   On mailbox input call the exact LiangHui operation and feed its actual
   structured receipt to the same PTY. Accept only cloud `video_ready` plus a
   same-hash `created|already_present` mailbox receipt as `Handoff完成`.

After Handoff, run the read-only acceptance gate:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_capture_acceptance.py \
  --identity <manifest-identity> --required-count 1
```

Require `status=passed`. Record the exact capture/source/task IDs, final filename,
SHA-256, duration/bytes, Netdisk job/cloud receipt, Handoff ID and mailbox hash in
the run's local evidence. Never call a code/test pass or `waiting` an E2E pass.
Mailbox `acked` is the separate remote `全部完成` state.

An explicit browser security-policy denial is not a transient OpenCLI timeout.
Stop the denied browser action and retain the upload claim; do not switch tools,
browser surfaces or protocols to bypass it. A submitted file without a cloud
receipt remains uncertain, even if another page shows an empty upload queue.
Do not resubmit or report Handoff until that exact job is safely reconciled.

## Continuation and completed-capture acceptance

On macOS the patched downloader owns a detached `__proxy-guard` pipe lease.
It snapshots HTTP/HTTPS/PAC settings before takeover, restores only its exact
endpoints before normal shutdown, and also restores after parent death (including
SIGKILL). Do not kill the guard or count it as a second capture process. Closing
a terminal (SIGHUP) follows normal cleanup. Preserve other software's later proxy
changes; never switch off every system proxy to force a green acceptance.
Cancel-wait must detach the owned PAC before stopping the sniffer, including on
inactive network services left behind by a network switch. Retain the existing
media/receipt validation gates. PAC uses `PROXY ...; DIRECT` for capture domains;
direct fallback preserves connectivity, not media-capture success.

If an older crash or machine restart leaves an orphaned endpoint, use the exact
installed downloader's `proxy-recover` subcommand (not a new capture). It refuses
a listening endpoint or active guard lease, touches only its own HTTP/HTTPS/PAC
configuration, and verifies readback. Without a prior snapshot it disables that
orphan, not a guessed previous VPN. Guard failures are logged in
`~/Library/Caches/wx_channels_download/proxy-recovery.log`; report them rather
than claiming cleanup. Power loss, simultaneous guard death, and denied system
configuration writes are not covered by a graceful-exit guarantee.

The full continuation remains enabled in code: exact-source media observation ->
original compressed download -> media validation -> detach only the capture PAC
and stop the sniffer -> original Netdisk upload -> hash-bound mailbox handoff ->
authoritative end-to-end readback. Do not insert a new permanent stop after native
playback.

Completed-capture acceptance uses the persisted, exact candidate/source/task
receipt and rechecks local media hashes; it must not restart or query the cleaned
sniffer merely to pass audit. A mismatched saved task fails closed.
