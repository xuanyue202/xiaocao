# Atomic Open → Allow

The human requested this on 2026-10-22 to remove model/dispatch gaps. Use the
reviewed controller for B1/B2 in **one `cua_repl.js` invocation**. Its internal
order remains two fresh stable-button reads → B1 → immediate read → exact brand check → PAC
checkpoint → fresh confirmation read → B2 → immediate brand read. Do not put
model reasoning, command preparation or a separate trace export between these
steps. “Atomic” means one controlled invocation, not rollback of external UI.

All UI still uses the documented CUA App API. Local compiled Vision processes
only the image bytes returned by CUA, deletes its temporary image, and derives
coordinates from unique current text boxes. It never captures a window, sends
native input, accesses mini-program DOM or uses historical coordinates. Strict
text/geometry matching fails closed on low confidence, ambiguity, changed App,
wrong brand, login/security, agreement, missing frame or rejected input. A separate read-only local window-metadata helper, compiled
and hash-bound before launch, requires one matching current-screen window and
screenshot geometry before each B1/B2 coordinate dispatch. It never captures or
sends input. A readable off-Space screenshot is insufficient.

After B1, the confirmation animation may take longer than the first screenshot.
The same invocation may read the same bridge, at most 12 additional frames or
eight seconds, until the exact brand confirmation is ready. B2 uses the same
bounded passive wait for the brand transition. This never repeats input or
uses Window-menu probes. Unknown/mismatched states and security stop. After
a returned B2 only, one failed same-App observation may recover through one
passive read, recording the failure; policy denial never retries.

## Prepare before the critical path

1. Keep the current original item and retained PTY. Already accepted media,
   download/upload or Handoff skips native activation entirely.
2. Complete Browser saved-target readback before native WeChat access, as in
   `native-share-bridge.md`. Record a private JSON proof with `identity`,
   `capture_job_id`, `observed_at`, exact `editor_url`, `component_reopened=true`
   and `saved_target` equal to the original share. No edit/save if already right.
3. Record the fresh canonical same-capture readiness as JSON: original identity/
   capture, `observed_at`, `singleton_healthy=true`, `same_pid`, current
   `network_service`. The runtime verifies the latest exact item's start/resume
   PID and scopes listener checks to that known PID, without owner discovery.
4. Issue/open one fresh merchant entry under the existing launch contract;
   preserve its original durable proof (`identity`, `capture_job_id`,
   `status=entry_launched_once`, `launched_at`). The macro issues no entry.
5. Prepare the plan. Compilation is cached by OCR source hash; prepare that
   binary before entry when needed to keep the critical path short.

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_prepare_native_atomic.py \
  --identity <original-subscription> --capture-job-id <original-capture> \
  --browser-proof <saved-component-proof.json> \
  --entry-proof <this-entry-claim.json> --readiness-proof <fresh-readiness.json> \
  --output <new-private-plan.json>
```

Use its emitted `cua_snippet` unchanged with the existing `wechat` App handle
after the permitted entry. This is one invocation labelled
`// KOL_ACTION:OPEN_ALLOW_ATOMIC`. Each input has a fresh frame, and each step
writes and fsyncs a hash-only event before continuing. A shared `O_EXCL` claim
is keyed by original capture plus the provider entry's canonical launch time;
changing plan or proof filenames cannot authorize another dispatch.

Original entry provenance remains valid for at most the runner's 20-minute
activation deadline, allowing a zero-input runtime repair to retain that same
entry without issuing/opening another one. Plan, Browser and readiness proofs
still expire after three minutes; the two fresh stable B0 reads and the original
one-dispatch claim remain mandatory. This does not extend the retained stdin deadline.
An explicit
`resumePreinput:true` may resume the same unchanged plan once only when its
durable original audit proves a legal paired B0 prefix with hashes, no dispatch,
no rejected/security/authentication/consent state, and an allowed terminal
preinput failure. It creates a supplementary claim preserving the old claim and
audit; fresh proofs and the same current readiness are still required. An unknown
effect consumes that entry. A stopped macro means diagnose the same item;
never create another plan/entry merely to repeat B1/B2.

At the verified Allow boundary, normal capture checks the exact healthy process,
listeners/API and current network service, applies/readbacks only the owned PAC,
then independently re-reads the confirmation before B2. Direct B1 → brand
without that boundary stops, because autoplay may have preceded capture.

## Audit and continuation

The one real source call contains durable `KOL_ATOMIC_EVENT` subevents with
timestamps and image/AX/target/proof hashes; raw text, images, credentials and
issued URLs are excluded. The exporter binds these to the original identity,
capture and real enclosing call ID. It does not invent per-action call IDs.
Export once after return and before another native input. Pending source output
or a missing/malformed subevent tail is `evidence_incomplete`; preserve the
actual transcript and the private `.events.jsonl` until readback catches up.

`brand_ready` is navigation proof only; `media_accepted=false` always. Continue
the existing password, finite-replay, B4 closure, download, cloud and mailbox
gates. Those actions retain their normal separate input/readback calls.

A **current human-authorized UI-only diagnostic** may use `--mode diagnostic
--diagnostic-authorization-sha256 <hash-of-current-human-authorization>`. It
requires fresh Browser/entry proofs, PAC off and both capture endpoints proven
absent (only explicit connection refusal qualifies). It neither starts a
capture service nor changes PAC, creates a job, downloads, uploads or sends a
mailbox message. This exception is not a scheduled completed-course replay or
an authentication retry; stop immediately on security/login or denial.

## Measured acceptance (2026-10-22)

A PAC-off UI-only diagnostic completed B0 → B1 → confirmation render wait →
checkpoint → B2 → brand readback in one real CUA call: 5,409 ms internally,
5.505 s tool wall time. Its 23 timestamped hash-only events were accepted by
the exporter under the real enclosing call ID. Earlier failed/partial attempts
remain in the same run; the overall historical trace still reports incomplete
evidence for the earlier unreturned observation. This is navigation validation,
not another capture or proof of a WeChat-protection cause.
