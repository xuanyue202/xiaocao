# Independent missing-video diagnosis

Baseline4ff0b64. Human requested independent monitoring when Xiaocao goes
consecutive trading days without obtaining video: proactively inspect exact
WeChat records and escalate problems, rather than depending on capture source
health or the user noticing omissions. Existing user exclusions remain effective.

Implement a read-only watchdog independent of source execution/locks. Use the
exchange calendar; default trigger is two completed trading days with no valid
media receipt. Complete the video day at22:00 China time; separately expose any
announced original older than6hours without recorded Handoff. Cover intervening
weekend/holiday backlog since the preceding third trading day and recently changed
older items, without reviving all untouched legacy history. Count actual media
receipt dates separately from original course-date coverage; acquisition today
clears an active no-acquisition streak. Distinguish media receipt vs local Handoff
vs remote ACK using bound recorded evidence, and diagnose
fresh paginated exact-contact cached history. Failed/incomplete history/calendar
is degraded, not no_update. Never start native/PAC/capture/upload/mailbox effects.
Output only credential-free identity/stage evidence; own status/fingerprint
deduplicates unchanged notifications. Notify new/changed actionable gaps and
recovery in this existing chat. Keep routine capture cadence unchanged.

Add a separate thread heartbeat via Automation API after validation/review; do
not create a new chat or edit TOML mirrors to activate it. Readback verifies the
saved cadence and prompt. Production business acceptance stays receipt-bound.

Independent Standards/Spec review fixes: ACK is a separate same-handoff/content
recorded receipt; acquisition counts use actual media validation time, with
source-date coverage separate. Read bound capture/event progress before filtering
old manifest items. Generic legacy expiry metadata does not revive an old source.
Notification fingerprints exclude ordinary progress timestamps. Both final
reviews report zero remaining actionable findings; nine focused tests and219
affected tests passed. Manual read-only history checks found existing backfill
gaps and today's original missing from discovery; no native or media effects
were used for watchdog validation.
