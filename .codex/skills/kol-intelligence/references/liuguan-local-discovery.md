# Liuguan local metadata companion

This is the user-authorized Liuguan/养生自行车 source addition, not an investment
source or a remote KOL writer. Read it when the local Automation asks to discover
吴老师的朋友圈直播. Leave the ordinary Xiaocao capture lifecycle intact.

After the single hourly gate returns `hour_acquired`, while retaining the same
PTY, execute once from the local Xiaocao checkout:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_yangsheng.py discover
```

This reads cached messages and Moments through the installed local WeChat reader.
It never starts the sniffer, changes PAC, opens WeChat/browser pages, downloads
media, runs ASR, writes investment data, sends messages or claims a handoff.
`hour_busy` still ends the invocation immediately; do not run this companion then.

The adapter lives under the existing Vault `_system/yangsheng-capture/`; the
private queue lives under `~/.codex/yangsheng-capture/`. A missing adapter, failed
read or malformed record is `source_failed/source_unavailable`, never `no_update`.
Cache discovery does not prove fresh server discovery or complete Moments
coverage. Preserve pending cards and report that limit.

The exact contact is `wxid_02jgv2ozgk3r12`. Recent cards identify the channel
六观小院-町原 and contain independent `finderLiveID` values. Preserve the original
Moment ID/hash and publisher/live/object IDs; repeated shares of one live ID
remain one candidate. Unknown publishers remain `author_verification_required`.
Cached `liveStatus=1` is not present-tense live/replay readiness. The historical
wxwork_live recordings are a different source route, not current replay proof.

Current acceptance boundary: metadata discovery is implemented; actual current
recording capture, cross-source native/PAC serialization and scheduled media/ASR
are NOT accepted or enabled. Keep candidates at `awaiting_replay_metadata`; do not
fabricate a media URL, bind an unrelated historical capture, create an upload,
send a mailbox message or report a transcript/course as complete.

The current diagnostic observed a Browser site-safety denial for
`channels.weixin.qq.com`; it did not offer an approval prompt. Never use another
browser, raw browser commands, a proxy or another surface to circumvent a denial.
A future real-media stage requires an actually granted, supported access path
and independent source/media/finite-duration acceptance before activation.

For the known main-chat white screenshot, use actual target-window readback.
The Oct21 diagnostic selected an already-existing independent mini-program
through the fresh native Window menu and read its real content successfully.
This proves the main-chat white image is not a global screen-capture failure or
logout; it does not prove the cause of the blank Qt window or authorize blind
main-chat clicks. Do not repeatedly ask the user to unlock a normal, unlocked Mac.
