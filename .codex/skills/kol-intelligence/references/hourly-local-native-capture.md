# Hourly Local Native Capture Stages

Read this reference completely at the native launch, identity-resolution,
activation, or continuation/acceptance stage routed by
[hourly-local-capture.md](hourly-local-capture.md), including resumed jobs.
Keep the existing capture/job and process; the local entry owns discovery,
process lifetime, and mailbox completion.

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
Confirmation may automatically start playback. Immediately press `space` in the
player window when playback starts, before querying logs or download progress.
If it does not auto-start, click the visible Play control once then press `space`.
Verify that the picture/playhead stops on two observations; a cursor triangle,
successful click, or disappearance of controls is not pause evidence. Never
press Space a second time on an already paused video, as it resumes playback.
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
   visible course-password gate, then immediately pause with Space after auto-play
   (or one visible Play click). Read back a stopped picture/playhead. Let the target
   start a media request; no continuous playback or fixed wait is required. Return
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

以下步骤以 2026-09-06 晚场实际抓取为依据。商户唤起、课程口令、空格暂停、
完整回放下载和压缩均已验证；最初点击暂停失败，不能复用那次点击方法。
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

   用 `cua_repl` 获取微信（首次调用只执行这一行）：

   ```javascript
   var wechat = await cua.getApp("com.tencent.xinWeChat");
   ```

   在后续调用中用 `await wechat.getAXStateAndScreenshot()` 读取**鹅直播课程窗口**。
   核对场次标题；主聊天窗口白屏不代表退出。AX 有控件就用控件；仅暴露窗口时，
   按刚读取截图中的可见控件点击，不存固定坐标。逐个动作后读回：
   **输入密码 → 弹窗输入框 → `typeText("666")` → 确认框内为 666 → 确定**。
   没有课程口令门就跳过；不要把 666 输入微信账号登录框。

4. **画面起播，下一步立即按空格。** 口令确认后可能自动播放；一旦看到起播，
   下一次 UI 操作就是在同一鹅直播播放器窗口执行：

   ```javascript
   await wechat.pressKey("space");
   await wechat.getAXStateAndScreenshot();
   ```

   仅没有自动播放时才点一次可见 Play，然后立即按空格。不再试点底部暂停图标，
   不先切终端查日志，不连续播放等待下载。再观察一次，确认画面/播放时间停止；
   鼠标三角形、点击成功、控件消失均不算暂停证据。已暂停不要再按空格。
   若用户切了窗口，先重新读当前窗口，不能把空格发到错误应用。

5. **确认有限回放，交回原 PTY，等压缩文件完成。** 暂停后才查
   `/api/elive/live/candidates?all=1&view=capture`：候选必须是 baseline 之后出现、
   与当前 app/live ID 一致的有限 VOD `playlist_eof.m3u8`，不能选同时出现的
   `liveplay` FLV/M3U8。只读必要的 ID/时间/类型，不输出签名 URL、headers 或 cookies。

   向原 PTY 回一行当前请求指定的 JSON，原样保留动作和身份字段；只在实际读回
   后填写 `playback_surface=wechat_mini_program`、
   `page_state=mini_program_media_observed`、`activated=true`、
   `media_request_observed=true`、`playback_paused=true`，并据实填 `password_used`。
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
