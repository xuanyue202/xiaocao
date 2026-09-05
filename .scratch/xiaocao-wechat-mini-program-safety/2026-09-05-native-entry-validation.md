# Native entry repair and live acceptance boundary

Update: native launch, visible course password and a fresh exact-source finite
media request passed on Sep 5. Full download/upload acceptance is NOT passed.
The user explicitly deferred those later stages; no further download or upload
is authorized in this continuation. Earlier failed observations below are history.

## Sep 5 verified evening-entry result and routine path

- Target: `kol-wechat-9cf5f75a8a43bb900b34cddd`, Sep 4 17:01 share.
- Original URL: https://9znl4.xet.tech/s/2vTI0J
- Source: `xiaoetong:app6ums63as6516:l_6a9a64c0e4b0694c35463342`.
- Capture: `kol-41ec37cf0683`; source job `elive-job-d5a4b25f8c928407`.
- Merchant-issued Web Link produced a real URL Scheme. One normal macOS `open`
  launched a visible Goose Live window (12701). WeChat PID 84914 stayed unchanged.
- The window showed the Sep 4 evening replay and a course-password button.
  Agent entered `666` at that visible gate; the mini-program began loading media.
- New exact-live finite `playlist_eof.m3u8` candidates were observed at
  17:10:15–18, after the 17:08:24 arm (e.g. `204d58e61495897a`).
- No logout or protection prompt was observed during this sequence. This is
  one successful native-entry run, not proof of zero future protection risk.
- The original downloader auto-created tasks that errored with zero bytes; the
  mini-program later showed a replay-network error. No upload/handoff happened.
  Retain both failed tasks and the existing source/capture identity. At deferral,
  source task was `GzqGCYZRbDgkyTuCS9XLz`. The sniffer inherited a PATH without
  `/opt/homebrew/bin`; ffmpeg availability is a later-stage diagnosis, not a
  confirmed fix. Do not treat this deferred work as a provider/login blocker.
- Downloader and runner are stopped. Wi-Fi PAC URL restored to
  `http://127.0.0.1:33331/commands/pac`, disabled. Mini-program left open.

Routine implementation: `scripts/kol_xiaoetong_launch.py` is read-only, validates
the original share's app/live binding, obtains the official Web Link, excludes
the HTML mock branch, and checks that the real Scheme embeds the exact replay.
It emits a one-time launch command, not a playback claim. The default resolver
and activation requests now include this command, and the local capture skill
requires arm/PAC-before-launch, reuse of an existing target window, visible
password handling and positive sniffer evidence. Native-only tokens retain the
original-message fallback. Scheduling stays PAUSED pending downstream acceptance.

Candidate-list optimization: capture view reads observed candidates without
historical title enrichment or network HEADs; live measurement was 0.0325 seconds
for 1,078 rows (the old listing exceeded 40 seconds). General display enrichment
is asynchronous and incremental by file identity/size/mtime; cold scans cannot
block the list, unchanged files are not reread, and candidate rows remain fresh.
Historical JSON files are preserved, not deleted.

The current source/tests supersede the earlier binary hash and test counts below.

## Exact retained target

- Manifest identity: `kol-wechat-1075c4dd955977b3b748e55b`
- Capture job: `kol-4e5c505ccb5f`
- Entry: original Goose Live mini-program message dated 2026-09-04 08:37.
- Native entry has no confirmed app/live ID yet. Do not bind it to the Sep 3 H5 job.
- Existing arm is preserved; there is no download claim or new media receipt.

## Implemented locally

The history parser previously accepted HTTPS links only. It now discovers the
original Goose Live mini-program token with its contact, timestamp and message
hash. A native entry arms a candidate baseline before UI activation. The capture
driver verifies exact candidate ID, live ID, source app host, post-arm timestamp
and finite replay filename before binding media; signed URLs remain in memory.
Acceptance checks native capture/task labels as well as media validation and
handoff. Unknown UI state cannot satisfy the no-protection check.

The Go downloader has a Xiaoetong-only mode and a domain-scoped PAC. This mode
skips WeChat/security/chat/channel and arbitrary post plugins, overrides global
HTTP/TUN proxy settings, and does not install missing trust certificates. The
Xiaocao launcher supplies `--xiaoetong-only` on start and resume.

Go source: `/Users/bytedance/coding/wx_channels_download`.
Current local binary SHA256:
`53f7b4a55e5f68b360650eeaaecef040af7e42d9ae49e961732b781b27946651`.
The original binary is retained as
`wx_video_download_macos_arm64.pre-xiaoetong-only-20260905`.

## Observed UI and research

WeChat 4.1.13 passes `codesign --verify --deep --strict`. With the downloader
stopped and proxies disabled, one normal quit/reopen and Enter WeChat action
showed the login transition and then a white screenshot. The AX tree exposes
only the window, standard controls and menus. Chat and Search menu actions did
not expose usable chat controls. No target message was opened. The user later
confirmed that the physical display shows normal chat. The white image is an
observation-channel problem; it is not evidence that WeChat itself is blank or
that a new protection event occurred.

A first-hand report describes the same collapsed AX tree on WeChat 4.1.13:
https://github.com/huj28-creator/wechat-fastbridge/issues/1
This is corroborating evidence of a compatibility issue, not a proven diagnosis.

## Checks and retained environment

- Python focused suite: 202 passed; the additional native acceptance binding
  test also passed (acceptance module: 3 passed).
- Go `go test ./...`: passed.
- `git diff --check`: passed; local capture SOP: 7991 bytes.
- Exact live acceptance: failed, zero observed live IDs and zero new media.
- The existing local KOL Automation remains PAUSED.
- HTTP/HTTPS proxy disabled. Original PAC URL restored to
  `http://127.0.0.1:33331/commands/pac`, disabled.
- Downloader and interactive runner are stopped. Resume the same manifest and
  capture job after the visible UI issue is resolved.
- Changes remain uncommitted; unrelated WIP is preserved in both repositories.

## Continuation: observation/control boundary

After the user unlocked the Mac and requested continuation, CUA observed the
temporary "WeChat start group chat" contact picker. Escape dismissed it, and
the main window returned. No contact was selected, group created, or message
sent. The main window screenshot remained white and the accessibility tree
still exposed only standard window controls and menus.

Attempts to re-open the native contact picker did not produce a verified usable
search field. One screenshot attempt returned ScreenCaptureKit error -3811
(audio/video capture failed to start). Later reads again returned a white main
window. Selecting the system Screenshot app timed out and it did not appear in
the app inventory. The contact-picker paste alternative was not executed,
because a focused search field could no longer be verified. No unseen chat
coordinates, guessed mini-program URL, process injection, re-signing, or new
proxy activation was used in this continuation.

The Sep 1 task transcript also separates the old media success from agent UI
activation: media candidates existed around 16:08 China time; the recorded
agent click attempts began at 17:23, and the user reported logout at 17:26.
The candidate/download chain is evidence for media capture, not evidence that
those later clicks opened the mini-program successfully. The exact trigger for
the earlier playable request remains unproven.

Current resumption requires a usable, observable native UI control channel.
Do not resume scheduled capture or mark acceptance passed until that exists.
If the original message becomes inspectable, start the same capture job with the
Xiaoetong-only downloader, verify health, enable the narrow PAC, then activate
the exact original message once. Require a new finite media candidate, validated
download and unchanged normal WeChat operation before claiming a live success.
