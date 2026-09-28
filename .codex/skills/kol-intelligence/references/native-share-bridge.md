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

Read the local, untracked configuration at
`output/live/kol_xiaocao_live/native_share_bridge.json`. It holds the existing
editor/public page, provider application/path, button label and the last
configured subscription/message hash. It contains no ticket or signed media.
The config describes the bridge; the current request/manifest remains the source
of truth for contact, publication time, application name and original share token.

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

Bind `wechat` with `await cua.getApp("com.tencent.xinWeChat")` only when no
binding exists; follow the tool's first-use documentation. If the observed
Window menu uniquely lists “草料二维码”, select that item and read back its
page. Main-chat white screenshots are not proof that WeChat exited.

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
