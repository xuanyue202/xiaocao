# Retained Xiaocao capture and shared source priority

Status: implemented; current AM/PM originals accepted; historical file gaps retained

User request (2026-10-23): fix the two retained Local Capture runs, preserve
original tasks, avoid duplicate downloads, finish the real pipeline, and run
Xiaocao before 町原/Liuguan.

Baseline: c82688a.

Requirements:
- Existing healthy shared backend reuse must update original-capture PID
  evidence after verification, without spawning, rearming or changing baseline.
- Local Capture finishes Xiaocao and its handoff continuation before Liuguan.
- Outside-window runs must not start Liuguan. Shared cleanup still waits for
  all users/downloads; no destructive shutdown to satisfy priority.
- Generic embedded WeChat windows are not login or saved-target evidence.
- Verify retained Oct22 AM/PM identities with real native capture and exact
  downstream receipts; preserve historical missing-file claims and report gaps.

Evidence: the old capture stored PID 61386, while the verified shared binary/API
used PID 32620. Four regression cases failed before the fix;25 targeted CLI/start
and45 shared-runtime checks passed after repair. Both original Oct22 courses
completed native entry, finite download, validation, upload and exact mailbox
readback. The native fingerprint was closed and narrowly resumed without another
effect. Liuguan cycle9 then assessed all33 accounts with0 errors/0 new tasks;
5 complete ASR results were reused. Final cleanup proved process/ports gone and
all proxy flags off. Historical missing-byte claims remain explicit gaps.
