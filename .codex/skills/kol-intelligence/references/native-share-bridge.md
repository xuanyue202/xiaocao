# Native share entry through the reusable Caoliao code

Use for an original `#小程序://见势擒龙团/<token>` from the local capture request.
Read [hourly-local-native-capture.md](hourly-local-native-capture.md) first for
singleton readiness, PAC, finite replay binding and the downstream pipeline.
Keep the original subscription, capture, source, baseline and retained PTY.

## What has actually passed

On 2026-09-28, the Agent obtained a fresh Caoliao-issued entry, opened the
configured native code, clicked its course button and the visible “允许”, and
reached the original Sep24 `见势擒龙团` course. The singleton observed its finite
replay; the same capture was compressed, validated, cleaned up and uploaded to
`/课程/自己的课/小草`. LiangHui returned `created`; authoritative message/content/
media-hash readback and the one-item acceptance gate passed.

On 2026-09-29, Sep27 evening completed the same pipeline without user course
clicks or closure: fresh provider entry, native course/Allow, exact native v2
merchant response binding, compressed download, validation, capture-only cleanup,
Netdisk `video_ready`, mailbox `created` and authoritative same-ID/content/media
hash readback. One-item acceptance passed. The mailbox remained `pending` at
that readback: local Handoff, not remote acknowledgement or completed backfill.

The first Sep24 evening Handoff required user closure: the old File-menu action
did not close the newer branded window, and a fresh round-close click returned
`noWindowsAvailable`. The user closed it; the Window menu proved absence.
Later that day, fresh-screenshot round-close actions and Window-menu absence
readback passed for Sep28 live, Sep23 morning/evening, the single authorized
Sep23 morning repair, and Sep24 morning. These are bounded native-control
observations, not unattended batch Handoff acceptance. Sep27 evening's circular
close returned `windowNotFoundAtPosition` even on the current Space. In the
same-source repair, fresh File → `关闭全部标签页` (`performClose:`) closed the
actual brand course; the Window menu then proved absence. Prefer that semantic
close below. This repairs the workflow, not the underlying input service.

## Reuse the configured code and bind the original share

Browser first: before any native WeChat read or input, verify the configured
editor URL/code and independently reopen its saved original-share component in
the bound Browser tab. Do not call `cua.getApp` for WeChat, take its screenshot,
or select Window → 草料二维码 merely to prepare or verify the web editor.
If the saved target matches, skip editing/saving. Only after this Browser
readback verify the same capture's sniffer/PAC and obtain one fresh provider
entry; then bind/read native WeChat once for B0–B4. An exact course already
verified in this task may be reused without another launch. Do not open native
windows just to discover whether Browser editing is necessary. Fewer native
actions are not proof that WeChat protection cannot occur.

An already captured item's window-cleanup request skips editor checks and entry
issuance entirely; verify/close only its exact native course under B4. After a
known download/upload claim, follow downstream receipts without another launch.

Read the local, untracked configuration at
`output/live/kol_xiaocao_live/native_share_bridge.json`. It holds the existing
editor/public page, provider application/path, button label and the last
configured subscription/message hash. It contains no ticket or signed media.
The config describes the bridge; the current request/manifest remains the source
of truth for contact, publication time, application name and original share token.

The editor is a web page. Prefer Browser DOM controls bound to the exact existing
authenticated editor tab as the routine entry, before any
native action. Do not select native Edge/Computer Use to edit this page;
`cua_repl` native input uses the existing reviewed WeChat action tables, including
consent and course closure. This routing avoids
starting a web edit through a native input surface that may reject its URL;
it does not change or bypass a tool security policy. If this operation is
explicitly denied on any surface, stop it and diagnose the recorded boundary;
never switch tools to execute the denied edit.

Read `editor_binding` from the current local config when present. Reuse its
Browser/tab ID only after fresh metadata confirms the exact editor URL/code;
if stale, resolve the existing editor tab by the configured URL and inspect any
ambiguity. Use that tab's Browser DOM locators; do not use native `setValue`,
native Edge actions, or browser-wide foreground input. Re-read the tab URL
before each component read/mutation, and use locators bound to this same tab.
If the URL changed, stop before fields/input and rebind the existing editor.
An explicit policy denial stops the action on every transport.

OpenCLI is a supported fallback for a genuinely unavailable Browser transport,
only when exact-page readback succeeds before any editor input. In that path,
read `opencli browser caoliao state` first (use pinned
`npx --yes @jackwener/opencli@1.8.6` when needed). If its page is about:blank,
rebind this same session to `editor_url` from the current config with
`open <editor_url> --window foreground`, select the returned exact page with
`tab select <page> --window foreground`, and read state again. A disconnected
session or transient command timeout may receive bounded same-session recovery;
do not recreate the code, change identity, use CUA on the editor, or bypass a
policy denial. Inspect fresh visible component DOM before filling/clicking;
never reuse numeric references or CSS selectors from a historical snapshot.
Session name or an earlier state snapshot is not sufficient page binding.
Pass `--tab <exact returned page>` on each supported browser command. Both a
separate tab selection and an explicit --tab eval returned an unrelated URL
in the 2026-10-14 diagnostic; neither is acceptance without current URL readback.
Before each component read or mutation, require the current page URL to match
the configured editor host and exact code ID. For supported OpenCLI DOM writes,
keep that URL check inside the same evaluation; Browser read-only evaluate
must remain read-only and mutations use the bound tab's locators. Reject a
changed tab before inspecting fields
or dispatching input. Re-select the exact editor page and read back when the
user has changed the foreground tab; do not operate their unrelated page.

After a changed target is saved, independently reopen/reload the same editor,
reopen the component and verify the exact original share and generic button.
An unsaved field value, local config match, or Save click success is not proof
of persisted binding. Update local subscription/message binding only after
that verification, then allow the fresh merchant entry. If the saved target
already matches, perform verification without another save. Keep signed tickets,
credential values, hidden app state and guessed component APIs out of this path.

1. Skip activation when the same capture already has accepted media, an active
   download, an upload claim or Handoff. Continue its existing downstream stage.
2. In the existing logged-in browser editor, inspect the code's “其他小程序”
   component. For a different original message, edit that same component's
   **小程序链接** to the exact request share and save. Reopen its configuration and
   read back the exact target. Preserve the code and the generic button label.
   Record the new subscription/message hash in the local config only after this
   readback. Even for the same source, verify that the editor still targets it.
3. Use only the original native share string as the target. The successful path
   did not submit the card's personal tracking query to Caoliao. Its “文本”
   component is static display, not a visitor input bound to navigation; there
   is no verified component-update API or visitor-input launcher here.
4. An unavailable config/editor is an entry-repair problem. Inspect the existing
   account/code setup; do not create another code, change the course identity or
   delegate the ordinary course/Allow buttons to the user. Authentication remains
   a user-only boundary.
   Before any new entry, require the exact saved target readback; the local
   config alone is insufficient. If that readback fails, return
   `page_state=native_bridge_target_unverified`; if an explicit tool policy
   denies the edit, return `page_state=native_bridge_policy_denied` and stop
   that denied action without another-tool bypass. Both retain the original
   item for diagnosis, rather than claiming a provider replay wait.

## Obtain the fresh provider-issued entry

The observed first-party transport is
`POST https://nc.caoliao.net/api/weixin/getWxUrlScheme`, form fields:

```python
query = urlencode({"q": config["public_url"], "trigger": "h5_wx_block"})
fields = {
    "query": query,
    "path": config["provider_path"],
    "appid": config["provider_app_id"],
    "org_coding": config["provider_org_coding"],
}
# requests.post(endpoint, data=fields, timeout=20): form-encode once.
```

Inspect `data.wx_url_scheme`: require the exact configured `appId`; its decoded
`appPath` must be `/pages/code/code` with `q` equal to the same public page,
`trigger=h5_wx_block`, and the provider's `f=schema`. Validate the returned
`fetchUrl` as HTTPS on `wxurlgenerator.cli.im`, fetch it unchanged, and use the
fresh `data.urlScheme` unchanged through normal macOS `open` **once**, after the
original capture's readiness/PAC checks. Keep the ticket in memory; do not print
or persist it. The issued entry opens Caoliao, which then uses native navigation
to the exact original share; it does not sign a brand entry on Caoliao's behalf.

The previously verified free-code branch has provider AppID
`wx5db79bd23a923e8e`, path `/pages/code/code`, org coding `oZwrwZ`.
An extra manual encoding pass produced the wrong `q` and a loading-only window.
Read the current public page's first-party assets if its contract changes;
do not compensate by splicing a ticket. The 2026-09-28 sources were
[entry logic](https://h5.clewm.net/assets/index-DcbxUyn5.js),
[service](https://h5.clewm.net/assets/service-CVzg8Gv5.js), and
[encoding](https://h5.clewm.net/assets/normalize-B7glC2DX.js).

## Visible native jump: B0–B4

### Action evidence and an explicitly authorized diagnostic rerun

Use `scripts/kol_native_action_trace.py` to export the exact current task's
known rollout file (never discover another task/owner). Bind `--thread-id`,
`--not-before <this run's timezone-aware start>`, `--identity` and
`--capture-job-id` to the original request, with a per-run `--output-dir`.
The exporter only reads local evidence and the original manifest; it starts no
apps/services and changes no claims. It retains immutable source-hash snapshots
and a `latest.json` pointer. Image/code/text hashes bind original evidence;
raw images, typed text, credentials and issued URLs are not copied into reports.
Inspect `coverage` on every export: `source_before_run`, `no_selected_calls`,
an incomplete tail or pending outputs mean evidence is incomplete. A stale
current-task journal can return zero calls; this never proves no operation,
error or protection occurred. Preserve the actual tool transcript and a clearly
labelled manual observation record until that exact journal catches up. Do not
invent call IDs/timestamps or claim a full exported trace, and do not repeat
native operations merely to populate telemetry. Continue the original safe job.

Label each relevant tool call with a code comment `// KOL_ACTION:<STEP>`:
`BROWSER_PREFLIGHT`, `READINESS`, `PAC_ENABLE`, `PROVIDER_LAUNCH`, and the actual
native SOP step. For native inputs, split the table's action and immediate
readback into two consecutive tool calls, labelled e.g. `B2_ALLOW` then
`B2_READBACK`. This changes recording granularity, not permitted actions or
counts. Export after readback and before the next input; an unfinished tool
call is pending, never a successful action. Preserve the exact source call IDs
and request/output bounds. No added menus, screenshots or inputs for telemetry.

For an explicitly user-authorized diagnostic rerun after a security exit,
once Browser has verified the saved exact target, allow one passive native
authentication-baseline read before enabling capture PAC or issuing/opening an
entry. Label it `AUTH_BASELINE`. Use the existing WeChat handle when available;
do not select windows or dismiss prompts. If it already shows security/login,
stop before PAC/entry and return truthful authentication state to any retained
PTY. This baseline is evidence collection, not authority to log in or repeat an
unchanged route. The user must authorize the concrete changed diagnostic plan.
Captured-course cleanup and known download/upload stages skip this preflight.

On any anomaly preserve first abnormal AX separately from first explicit
security text. The exporter lists preceding effects, not proven causes: a
security decision can predate its UI. An offline trace/test pass is not a fix
for WeChat self-protection or actual media/cloud acceptance.

After the Browser/readiness/entry sequence, bind `wechat` with
`await cua.getApp("com.tencent.xinWeChat")` only when no binding exists; follow
the tool's first-use documentation. If the post-launch readback or B1/B2 result
does not show the expected bridge/brand state, do not add a Window-menu probe
or choose a window to chase the jump. One current-state readback then offline
diagnosis preserves the item. Independently verified-course cleanup retains
B4b/B4c. Main-chat white screenshots are not proof that WeChat exited.

## Security-relogin recurrence and attribution

The Oct14 23:25 original-item trace did not select any window item. It opened
the application's Window menu and cancelled it. At 23:28:15, before Cancel,
the AX window title was already empty, ordinary WeChat actions were disabled,
and no course/bridge was listed. At 23:28:24 Cancel's readback first exposed the
explicit security-relogin text. This supports an already abnormal window state
before Cancel; it does not establish whether the earlier Allow, networking,
menu opening or an asynchronous security decision caused it.

Do not infer a trigger from the last screenshot/menu action. Generic focus/menu
events can be observed by an application; that is not evidence about WeChat's
security policy. Keep dispatched actions, last normal state, first abnormal
state and first explicit protection text separate in the operation receipt.

After a security-relogin page, stop native inputs and preserve original IDs and
claims. User login restoration alone does not authorize replaying the unchanged
PAC → issued Scheme → cross-mini-program navigation chain. First identify a
concrete evidence-backed changed repair/diagnostic plan and its applicable
authorization; use offline validation before any approved bounded probe. Do not
turn relogin into a retry loop, move to another tool after denial, add arbitrary
delays/count limits, or treat an offline pass as root-cause/E2E proof. Existing
capture cleanup and authentication response requirements still apply.

For every click use a unique fresh AX index, or the center of the unique visible
control in the latest screenshot if AX lacks the control. Follow each action
with the indicated observation; no historical coordinates or blind input.

| Step | Required visible state | Action and readback | Result |
|---|---|---|---|
| B0 | Fresh issued entry opened the configured Caoliao page; editor target was read back | `await wechat.getAXStateAndScreenshot()` | Require the expected page and generic course button |
| B1 | That page's unique course button is visible | `await wechat.click(courseButton); await wechat.getAXStateAndScreenshot()` | Exact-brand confirmation → B2; exact course already visible → B3 |
| B2 | “即将打开‘见势擒龙团’小程序”, with unique “允许” | `await wechat.click(allowButton); await wechat.getAXStateAndScreenshot()` | Require exact brand course; this normal navigation confirmation is already in capture scope |
| B3 | Brand/course visible | Follow native W1–W6 only for a visible password/Play gate; otherwise inspect the same singleton candidate | Bind the post-arm finite replay to the original source; liveplay/warm-up are not acceptance |
| B4a | Exact branded course/title verified; its finite replay observed, or its waiting/live state established; no unrelated tabs/windows would be closed | From fresh AX click File; read AX, then click its unique enabled `关闭全部标签页` (`performClose:`) once and read `getAXStateAndScreenshot()` | Require the exact course to disappear; menu-click success alone is not closure |
| B4R | B4a returned without an input error, but a fresh Window menu still lists the same branded course; cancel that menu, then obtain a new screenshot of that exact course; its top-right mini-program circular close control is uniquely visible and unobstructed | Click the center of that current screenshot's close control once, then read `getAXStateAndScreenshot()` | Continue B4b–B4c only after the course disappears. A rejection or still-present course stops close inputs; no second fallback, relaunch or WeChat-main-window close |
| B4b | Course disappeared; fresh AX gives unique Window menu | `await wechat.click(windowMenu); await wechat.getAXState()` | Require no `见势擒龙团` window; still present means unverified, no repeat close |
| B4c | Window menu proved absence and exposes `Cancel` | `await wechat.performSecondaryAction(windowMenu, "Cancel"); await wechat.getAXState()` | Record `playback_window_closed=true`; media/source acceptance remains independent |

There is no verified way to suppress “允许”. A separate service agreement or
sensitive permission uses C1–C3, not B2. If a click is rejected or times out,
read back once, record its actual stage/state and continue Agent-owned diagnosis
under the same job. `noWindowsAvailable` can occur despite readable AX/screenshot;
relative coordinates do not repair the app-scoped input-window selection.
Rebinding and a fresh observed Window-menu selection may diagnose the target;
do not turn a returned `open`/click success into course or closure evidence.

For this newer brand, never claim the old `关闭全部标签页` succeeded solely
because it was clicked. B4a–B4c require this round's actual result, not another
course's historical success. If the course is already absent from a fresh Window menu,
record that observation and skip another close. A known download can continue
while native closure is repaired; preserve both facts independently.

B4R is the bounded fallback for an observed no-effect semantic close, not for
an uncertain/denied input. It uses only the actual course screenshot, never a
historical coordinate or the main chat window's close button. The existing
round-close observations above justify trying this visible control; they do not
prove this round's closure. Window-menu absence remains mandatory acceptance.

## Input-window recovery, not a playback retry loop

`noWindowsAvailable` is an input-window lookup error, not proof of WeChat
protection or course entitlement failure. On 2026-09-28, the installed native
service used an on-screen-only window list for input, while screenshots used
desktop-independent capture. A single monitor can have multiple full-screen
Spaces: readable AX/screenshots do not prove an input-eligible current window.
One controlled Space switch restored the identical Calculator control without
restarting anything. Do not infer an off-Space cause from the error alone.

After a rejected action, read back once and distinguish actual absence,
off-current-Space evidence, and an on-screen window-matching failure. Use only
documented CUA targeting/AX actions; no blind coordinates, service injection,
permission changes, or operation of an app that the tool forbids. If a Space
switch cannot be performed through permitted controls, state that limitation;
restarting WeChat is not a demonstrated fix. The controlled desktop test is not
a routine request for the user to click a course.

For a visible Caoliao bridge whose coordinate input still fails on the current
Space, one bounded reconstruction passed: with no course open, no accepted
media/download/upload claim, and the original capture retained, close only the
bridge through fresh File → enabled `关闭全部标签页`; verify its absence from
Window and cancel the menu. Re-read the exact original editor target, obtain
one new provider entry after the same readiness checks, and execute B0–B3.
Do not repeat reconstruction if input remains broken. Never restart the singleton
or replace the capture for this repair. If the branded course is open, use B4;
do not reconstruct/replay merely to fix its close button. Fresh on-screen brand
coordinate close still failed in the repair test, while B4 semantic close passed.

## Continue to local Handoff

Return the existing request's exact response fields to its PTY. A finite replay
requires the singleton candidate and source checks; frontend arrival alone is
insufficient. The driver owns compressed download, hash/duration validation and
the capture-only PAC/sniffer cleanup. Do not restart a cleaned sniffer for audit.

Follow [opencli-baidu-netdisk-upload.md](opencli-baidu-netdisk-upload.md) with the
same hash-bound upload. Its file-URL-permission repair has also passed: after the
user restored access, `resume_pre_attachment_upload(...,
session="site:baidu-netdisk", file_access_restored=True)` reconciled the old
permission-failed claim, submitted once and completed. An attachment or
`upload_pending` remains nonterminal. Keep the same PTY through exact cloud
`video_ready`, exact emitted LiangHui arguments, the actual compact response,
authoritative readback and the acceptance command from the native reference.

Do not add expired merchant-link, plaintext Scheme, `launchapplet`, generic URL
helper or H5-player attempts to the routine route. Those experiments did not
prove the current branded course entry. Historical HTTPS entries are supported
only through their current emitted, identity-validated resolver; a past ticket
is never a replacement for the current native share.
