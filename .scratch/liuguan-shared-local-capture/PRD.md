# Shared local capture for Liuguan

Human authorization, October 22: end-to-end implementation; scan the fixed 33
Channels publishers, merge/sort replay metadata and capture new recordings;
read Wu's cached Moments for missed/new accounts. Use the existing Xiaocao
local-capture timing and the same wx_channels_download singleton. Keep ASR,
Xiaocao upload/handoff, investment semantics and current task identities intact.

Use the compatible Gopeed runtime, opt-in Channels plugins on only
channels.weixin.qq.com/res.wx.qq.com, no login/chat plugins. Keep existing
Xiaoetong PAC unchanged; a separate bounded narrow Channels PAC is restored.
Preserve old capture mode when opt-in is absent. Preserve active tasks and keep
all original claims. Existing Xiaoetong cleanup must not terminate shared tasks.
The original blocked /web/pages/home remains blocked.

Private durable catalogue: initial 274 replay baseline is observed history,
not a download backlog. Import the 3 verified files with their actual hashes;
new replay IDs after baseline are captured once. Failed/partial scans preserve
old history and pending work. Publisher/replay/time/duration binding precedes
any POST; pending intent survives unknown outcomes. Real artifact acceptance
is separate from metadata discovery. Fresh native session is needed; connection
failure is visible, never a no-update claim. No independent schedule.

Baselines: Xiaocao af01e19eeed9a7b0c68c2ee3ca140017ed1b1acc;
backend 74d27e4592ae1d5145ed9be732e2e164033ab64c, worktree
/Users/bytedance/coding/wx_channels_download-shared-capture.

User lifecycle clarification: this is one Local Capture activity with two sources.
The system PAC is temporary and is disabled immediately when page metadata
capture no longer needs it; background downloads do not extend its lifetime.
Downloader process shutdown is separate: only after all shared tasks and media
post-processing/acceptance finish, with a retained closing barrier.

October 22 latest human instruction: finish real shared capture/Local Capture
acceptance and then cut over; also connect accepted Tingyuan/Liuguan downloads to
the existing ASR end-to-end. This supersedes the earlier ASR-out-of-scope boundary.
Keep source replay identity, file hash, original video timeline and resumability;
no course-system organization, terminology editing or Xiaocao ASR changes.
