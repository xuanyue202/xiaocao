# Retained Xiaocao capture and shared source priority

Status: implementing

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

Evidence so far: the old capture stored PID 61386, while the verified shared
binary/API used PID 32620. Four regression cases failed before the fix, five
focused cases passed after it. The same AM capture opened its exact Oct22
course, verified ended merchant lineage, closed the course, and started its
original download. Download, cloud and Handoff acceptance remain in progress.
