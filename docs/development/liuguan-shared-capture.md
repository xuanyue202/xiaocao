# Liuguan in the shared Local Capture activity

Implementation is opt-in and **not deployed**. The production downloader binary,
private configuration and Automation have not been switched. ASR and Xiaocao
upload/handoff behavior are unchanged. No second schedule is introduced.

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

## Validation and remaining acceptance

376 scoped Python regressions pass; API/interceptor/proxy Go tests pass. Both
independent Spec and Standards reviews have no remaining blockers. These are
implementation checks, not shared-production acceptance.

The independent upstream path has three real recordings accepted. The compatible
shared candidate has not yet downloaded a real recording or passed native
cold-start acceptance. The prior native feed window is no longer present; the
main WeChat window remains protected and lacks readable content controls.
Do not activate the Automation or mark the shared flow accepted from the
independent files, metadata inventory, API availability or these offline tests.
