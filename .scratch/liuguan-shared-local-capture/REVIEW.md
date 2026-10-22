# Review record

Baseline Xiaocao af01e19eeed9a7b0c68c2ee3ca140017ed1b1acc; backend74d27e.
Latest incremental ASR baseline e0d96f2; unrelated origin/main Book B changes
fast-forwarded to9e493fc without overlap. Scope: additive Liuguan package/CLI,
shared Gopeed lifecycle and accepted-artifact ASR; no Xiaocao handoff changes.

Independent Spec and Standards reviews verified fixes for exact-host routing,
async decryption before shutdown, create/close races, false already-closed claims,
cleanup idempotence, invalid-cancel proxy effects, ASR writer-lock startup race,
bad-course isolation, malformed receipts and coordinator exception compatibility.
Final follow-up: scan failure dispatches accepted ASR after writer lock unwind;
the behavior test mocks private seed initialization and uses only temporary state.
Both final reviews: zero substantive blockers. Reviewers made no live API/UI or
process calls. 403 scoped Python tests and focused Go tests pass.

Real implementing-agent evidence: three independent recordings accepted and fully
transcribed; compatible private Gopeed re-download533314434bytes, same-task
pause/resume, same SHA, AV/duration/full packet and full ASR/idempotence accepted.
The compatible task uses retained accepted native media, not fresh discovery.
Native automatic reconnection and a complete shared Local Capture remain pending;
production binary/config/Automation were not switched.

## Native reconnection and publisher scan fixes (2026-10-22)

Baseline 791fe990bda45d4bca94db8ee0a862032ed7e26e; scope is the seven
Liuguan native/scan/SOP/test files. Independent Spec and Standards reviewers
reported no substantive defects, including follow-up review of the legacy
null/zero duration compatibility. 55 focused shared-capture/ASR tests pass;
the unknown-duration regression reproduced the real binding failure before
the fix. Existing positive-duration and publication-time changes still fail.

Real native search opened the verified publisher replay without Wu navigation.
Private bootstrap connected the SDK and restored PAC. Full scan attempted all
33 publishers: 28 successful, four empty provider errors and one timeout;
275 catalogue rows, degraded coverage retained. A fresh SDK media download
Q1cKzYN5z7ydpB-OQDQPc hit a network deadline with 1160683093 bytes retained.
Resuming that same task accepted 1161776599 bytes with AV, duration, complete
packet read and SHA 698b85ea3f48cf240d7d315de507bae8b5fbcd5d7d5f91e2f64a6632a9992a91.
Full ASR of this fresh file is in progress. Production cutover is still pending.

## Minimal native reconnection (baseline fe64eda)

Independent Spec review found a 90-second handshake versus 60-second PAC
guardian conflict and unbounded partial-line input. Both were fixed: the complete
line has a 30-second monotonic deadline and 64-byte bound. Standards and follow-up
Spec reviews have no remaining blocking findings. Slow system calls can still
fail bootstrap safely; no claim of guaranteed connection. 67 focused tests pass,
including a real pipe partial-input deadline, PAC recovery on callback failure,
lifecycle exclusion, CLI wiring and zero-input socket reuse.

Production native connection was verified through one CUA File/Refresh of the
retained replay tab and the existing network guardian; PAC restored. Subsequent
CLI bootstrap returned reused=true/proxy_changed=false with no native action.
Original 139 tasks,1729 candidate identities and capture ledger survived the
reviewed guarded binary/config cutover unchanged. Original 180-second hourly
companion input expired during investigation; source_busy skipped Xiaocao and
cleanup preserved the backend. The narrow companion continuation ran, but stopped
on a native API error after six successful publishers, so the whole shared
activity and full latest coverage are not accepted. Do not rerun the hour gate.
