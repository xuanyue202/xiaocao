# Liuguan in the shared Local Capture activity

Implementation is opt-in and **not deployed**. The production downloader binary,
private configuration and Automation have not been switched. Accepted Liuguan
artifacts now feed the existing local ASR engine; Xiaocao upload/handoff behavior
is unchanged. No second schedule is introduced.

The fixed 33 publishers are the primary sweep. Authenticated native replay lists
provide IDs, publication times and finite durations. Wu's exact cached Moments
supplement missed/new publishers; local cache absence never proves server absence.
The private catalogue initializes from the accepted 274-replay inventory and
three verified files. Other historical rows are observed history, not a backlog.
New recordings get namespaced task labels and retained pending intent before POST;
uncertain creation is reconciled rather than retried blindly.

The shared backend remains the existing Gopeed engine. A reviewed additive build
opts into only the Channels plugins alongside Xiaoetong; the standalone upstream
Hermes binary is not a compatible in-place replacement. Production activation
requires a matching private `~/.codex/yangsheng-capture/production/shared-enabled.json`
with the installed binary path/hash. Without it, capture-local retains the old
behavior and output.

## Proxy and lifecycle ownership

There is one Local Capture activity with two sources. Keep the temporary system
PAC while either source still needs it. A source finishing first cannot detach
the other source's proxy. Downloads do not themselves require the system PAC.
When page capture no longer needs it, detach the owned PAC; actual downloader
termination waits separately for shared tasks, decryption and artifact acceptance.

Native connection/scan users hold a shared lifecycle lease. Final cleanup holds
its exclusive counterpart through owner validation, proxy detach, drain and
actual termination. Native input and PAC initialization additionally take the
compatible legacy/source leases. Unavailable leases preserve the current owner;
never kill, unlock or replace its tasks. Cleanup validates capture ownership,
new candidates and existing strict receipts before changing anything. Paused,
uncertain or failed media remains unfinished. `done` alone is insufficient:
post-processing must finish and actual bytes, AV tracks, duration, full packet
read and SHA must pass. API failure alone is not process-gone evidence.

Liuguan uses a bounded exact-domain PAC during a freshly verified native feed
refresh, then restores the original configuration. Foreign proxy configuration
is preserved. The previously denied `/web/pages/home` stays blocked.

## Accepted-artifact ASR

`PYTHONPATH=src .venv/bin/python scripts/kol_yangsheng.py asr` consumes only
verified catalogue artifacts. Optional `--replay` selects an accepted ID. A
single serial worker verifies upstream proof, actual file hash, engine receipt,
original sample coverage and transcript hash, then writes a source-bound receipt.
The unchanged local engine still truthfully describes a local file; the adapter
separately proves its native replay/download origin. Original live IDs remain
unverified. Corrupt or changed individual courses are isolated; completed results
are revalidated and reused. No course organization or terminology correction.

A Local Capture invocation and successful final cleanup wake the worker without
a new schedule. A native scan failure still wakes already accepted courses after
the writer lock has unwound. ASR does not hold the system PAC or capture lease.

## Validation and remaining acceptance

403 scoped Python regressions pass; API/interceptor/proxy Go tests pass. Both
independent Spec and Standards reviews have no remaining blockers.

The independent upstream path accepted three recordings. All three now have
complete ASR and idempotent transcript readback. A compatible private Gopeed
candidate also downloaded replay 15037310283662367768 as task
kULIgOK7CV-IAtk6VYAAC (533314434 bytes), paused/resumed that same task,
matched the accepted original SHA and passed AV/duration/full-packet checks.
That new file separately completed full ASR and idempotent readback.

Fresh native reconnection is now verified on the private compatible backend:
one native publisher replay page connected the SDK and restored PAC. The latest
cycle attempted all 33 publishers: 28 succeeded, four returned empty provider
errors and one timed out. These remain explicit coverage gaps, not no-update.
The catalogue contains 275 observations. SDK zero and missing durations both
mean unknown; neither can create a download.

Fresh replay 15036599111904070751 was captured as task Q1cKzYN5z7ydpB-OQDQPc.
A real network deadline near completion recovered on the same task; all
1161776599 bytes passed AV/duration/full-packet/hash checks. The new file is
undergoing complete ASR. Production cutover and a complete shared Local Capture
activity remain pending; the private acceptance does not claim those steps.
