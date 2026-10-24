# Observe actual session protection before attempting native capture recovery

Baseline bbfc4c3. The user requests continued Mac direct-entry/authentication
recovery and end-to-end capture, without Moments UI or disrupting Xiaocao/ASR.
The actual11:44 readback now contains a visible security re-login prompt; the
proposed native event was not sent. Earlier absent socket checks did not tell
this apart from a closed page. This change is a diagnostic dependency, not a
claim that the user's whole capture task is complete.

Expose an explicit session-status CLI that reads only the existing vendor app's
AX and visible-window metadata. Do not activate/open/click/screenshot, request
permissions, extract keys, change PAC/holds/backend/tasks or run ASR. Match a
fresh visible window's exact protection message and acknowledgement button;
never infer authentication when absent/unreadable. Reject malformed, stale and
unbound evidence. Preserve backend-only connections and all existing captures.
Record primary-source entry capability boundaries and the actual human-only
authentication blocker. Independent Spec/Standards review, scoped regression,
real read-only observation and commit/push are required.
