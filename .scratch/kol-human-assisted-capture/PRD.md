# Human-assisted Xiaocao local capture
Status: implementing
Baseline: 95a3b69e209369b87c722bf7b2881df00051a409

Human request (2026-10-26): restore current code, detect new courses, start the existing wx_channels_download singleton, enable listening and awaken only the verified Caoliao mini-program. The human owns Open, Allow, consent/password/playback and all subsequent WeChat UI interaction. Keep waiting in the same local capture process; observe downloader HTTP/media evidence at 10,20,40,80,160,300 seconds, capped at 300 seconds. Notify the local desktop once when human action is needed; no notification on unchanged polling.

Requirements:
- Explicit private bridge setting selects human mode. Preserve the default legacy mode and its existing holds; human mode must never invoke CUA, screenshots, AX, native input or automatic playback/closure.
- Reuse exact original subscription/capture/task and baseline; preserve uncertain launch/download/upload claims. Launch once after saved target and listener/PAC checks. No automatic re-open while waiting.
- Opaque share tokens do not prove a live identity. For an unbound original, propose only the previously verified brand merchant; require one direct human confirmation of the exact course/source binding before accepting media, then retain it for restart. Never turn global freshness into course identity.
- Poll only downloader HTTP state and singleton-owned native merchant/finite-media evidence; bind a unique fresh source with existing lineage gates before any download. Reject stale, live or ambiguous candidates, changed app/live IDs, and existing unrelated tasks.
- Backoff and entry state persist across runs. The runner follows a human wait in the same PTY and source slot, and does not prematurely close the shared backend/PAC. Known media proceeds through the existing download/validation/upload/handoff flow.
- Human-mode course-window closure is human-owned, never fabricated as verified; it does not authorize agent UI actions.
- macOS-only action-needed notification, at most once per real course entry; no external messages. Notification submission is not proof it was displayed.
- No Liuguan/ASR changes. No historical experiment scripts selected. Tests, independent Spec/Standards reviews, then one retained real-item run; no production activation claim until actual media proof.

Human notification correction: use the normal Codex/ChatGPT question notification, not a custom persistent dialog. macOS controls Temporary/Persistent banner style; permission and style are separate. Emit one exact-course human-action event, ask asynchronously and keep HTTP polling. Do not claim notification display from a submitted event.
