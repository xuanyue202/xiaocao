# September 3–5 backfill and upload repair

User authorized all available morning/evening sessions for these three calendar
days, retaining original identities/jobs. Xiaoetong H5 playback/login is excluded;
use native WeChat mini-programs. The source contact's current bounded history has
four session announcements on Sep 3–4, no Sep 5 session announcement.

## Verified local media

| Session | Capture | Netdisk job | Bytes | Duration seconds |
| --- | --- | --- | ---: | ---: |
| Sep 3 morning | kol-baca37b68a8f | kol-netdisk-58e2474e4c2170e6 | 142224644 | 3721.150685 |
| Sep 3 evening | kol-94c10e660f59 | kol-netdisk-fbec95873ac0785b | 287021465 | 4682.12 |
| Sep 4 evening | kol-41ec37cf0683 | kol-netdisk-cc466a7032f969ff | 192762240 | 1822.767123 |

Sep 4 morning remains uncaptured, identity kol-wechat-1075c4dd955977b3b748e55b,
capture kol-4e5c505ccb5f. Original native token is retained; no guessed conversion.
No mailbox handoff or cloud-completion receipt exists for these three local files.

## 5 Why and bounded repair

1. No cloud file: original adapter command failed before recording submission.
2. Exact Sep 3 evening error (exec session 60811):
   `Page.fileChooserOpened not received within 5s — the input may not have opened a file chooser`.
3. Installed OpenCLI 1.8.6 / extension 1.0.24 programmatically clicks the input
   while waiting for a chooser event, then assigns file bytes only after that event.
   Read-only activation probe showed `userActive=false`, `focused=false`.
4. `--window foreground` plus tab selection did not establish browser user
   activation. One normal OpenCLI native click on the exact visible file-name
   header produced `userActive=true`, `focused=true`; the activation-only probe
   attached no file. No raw debugger workaround or extension modification used.
5. The wrapper collapsed the exact failure to `browser_command_failed`, so its
   exact-once guard could not distinguish known pre-attachment failure from
   uncertain submission. Regression now preserves a safe typed diagnostic and
   offers one explicit same-job pre-attachment continuation, never in a sweep.

The one repaired Sep 3 evening submission (exec session 27992) advanced beyond
the missing chooser event but returned `{"code":-32000,"message":"Not allowed"}`.
This is a separate local-file permission rejection; no upload_started_at was
recorded. Its repair attempt remains consumed; do not repeat automatically.
The other two historical generic failures have NOT been relabeled or retried.

Edge's exact installed extension details page was opened for user permission:
`edge://extensions/?id=ildkmabpimmkaediidaifkhjpohdnifk`.
No extension permission, preference file, WeChat protection setting, login, OTP,
or CAPTCHA was changed. Chromium's debugger API source explicitly requires file
access for DOM.setFileInputFiles:
https://chromium.googlesource.com/chromium/src.git/+/0fa0dfcb93a8691472237b1021728c1fa72fb937%5E%21/

The user explicitly enabled file-URL access at the next turn. The same Sep 3
evening job resumed once with `file_access_restored=True`, obtained a real input
receipt at 21:35:02, then exactly one cloud row at 21:40. That is a live pass of
the original upload failure; 96 scoped regressions subsequently passed.

The other two original generic failures were reconciled, not relabeled: exact
cloud counts zero, no target attachment/receipt/UI row, retained uploader fully
rendered (height/scrollHeight 349), and its one existing row was the successful
Sep 3 evening control upload. Both original jobs obtained a durable one-time
repair claim and submitted at 21:49:29 and 21:49:47 respectively. Both then
reached video_ready without duplicate jobs or full sweeps.

All three mailbox handoffs were created and their authoritative receipts fed to
the same retained PTYs, which exited normally:

- Sep 3 evening: e0fe3314f100b9a1cb24a151b9ee89c154cb9fe393b1413e6be6c820e5a3bb72
- Sep 3 morning: 54b735465fdfed4aefce5f76dd2a8ba6a4600a4ee48163b659922bf9045c5834
- Sep 4 evening: e880d76e2ad2102223cb916beb5af1504fc703463319005286baad3e7cc772b0

Sep 4 morning remains pending. The original task was resumed with sniffer PID
94211 and its narrow PAC only after all three cloud uploads finished. The
subscription prompt alone had not restarted the stopped sniffer; the exact
service start API restored the same capture job. Main WeChat chat remains
unobservable (blank screenshot and collapsed AX). A temporary native note did
not parse the mini-program token; its text was cleared and the empty note closed.
The user was asked to assist by opening only the exact original Sep 4 08:37
message. No Xiaoetong browser fallback, chat send, WeChat restart or hooks used.

Automation remains paused. Handoff completion is not remote analysis completion;
the fourth requested video is not complete.

## Acceptance readback

The repository acceptance command with all three exact subscription identities,
`--required-count 3 --not-before 2026-09-05T00:00:00+08:00`, returned `passed`,
`distinct_live_id_count=3`, and all fourteen checks true for each item. Completed
captures are now audited from their bound persisted task receipts instead of
calling the intentionally stopped sniffer; local hashes and ffprobe are rechecked,
and tampered candidate/task bindings fail closed. This does not assert an absence
of all possible WeChat protections; it proves no protection terminal was observed
for these exact accepted native captures.

The native activation path now calls `prepare_playback` before emitting its UI
request, requiring the same awaiting capture and healthy singleton. It cannot
substitute another job. The complete scoped suite passes 305 tests, including
the local runner and upload/handoff boundaries. The Sep 3 evening mailbox was
read back as `pending`; remote completion is not claimed.

At 22:14 the unanswered native-entry wait was suspended. No post-resume candidate
or running/waiting download existed. The exact idle sniffer 94211 was stopped,
the prior disabled Wi-Fi PAC restored, and all proxy flags/readback checks were
zero. Capture kol-4e5c505ccb5f stays awaiting_capture; the subscription is
awaiting_playback. The same PTY received a truthful media_request_observed=false
response and exited. Resume the same identity when the user opens its native
entry; do not create another job or leave the sniffer running between requests.
