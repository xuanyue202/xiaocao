# Restore the original closed live wait

Baseline: cef7b491c8ac626fe8cfa22263ff56d026f76290

The Oct15 original kol-wechat-dfb80b0c8f96e1f86d0ebb51 / kol-c9ee34cac249 is awaiting_playback with an observed live stream, activation false and course closure true. Global capture detection later set captured on candidate 9ff1a3037d26ea6b at liveplay-mp.xiaoeknow.com. No source/download/upload/media claims exist. prepare_playback rejects captured and cannot continue the original share.

Recover only this unbound closed live-wait shape through an append-only transition to awaiting_capture. Preserve the exact original ID/baseline and full live observation with source_accepted=false. Never accept/download the live stream, infer its app/source mapping, expire it as idle, replace claims or clear history. Every existing source/download/media/upload claim, ambiguous state, unclosed window, non-live host or mismatched candidate key must fail closed. Continue only the original share, with fresh finite media/merchant identity and all normal native/cleanup/upload/Handoff acceptance gates.

No changes to investment authority, schedules, external recipients or remote writer. Verify positive recovery/idempotency, claim safety, no historical auto-binding and no idle expiry.
