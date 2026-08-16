# Remote Video Player Safety

Read this before any remote Baidu player bind, switch, transcript capture, or
AI-note interaction for Lv Xiaotong, Xiaocao, or another Ticket 02 consumer.

## Pause before content work

Immediately after binding or switching to the exact player, install a
persistent pause guard and read back at least one `video.paused=true`. Muting is
not a substitute for pausing. Recheck the guard when switching transcript or
note views and again before final transcript capture; if playback is observed,
pause it immediately and record the readback.

Do not analyze content until the bound player has a pause receipt. A missing or
stale pause receipt is Agent-owned `repair_required`, not a provider wait or a
user blocker.

## Close after transcript proof

Persist the complete transcript first, then verify its exact path, DOM
completeness, order, and SHA-256. Immediately close every player tab for that
exact path by page ID and use `tab list` to prove no matching player remains.
Do not keep the page open for an ungated AI-note completion.

A missing close receipt is Agent-owned `repair_required`. Do not continue to
analysis, publication, notification, or Book effects until both pause and close
receipts are durable and bound to the exact player/transcript identity.
