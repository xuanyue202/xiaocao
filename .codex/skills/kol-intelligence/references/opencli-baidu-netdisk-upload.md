# OpenCLI Baidu Netdisk Upload

Use the repository-owned `baidu-netdisk/upload` OpenCLI adapter only through a
hash-bound `NetdiskEnrichmentService` job. Install or verify the exact template:

```bash
.venv/bin/python scripts/install_opencli_baidu_netdisk_template.py
.venv/bin/python scripts/install_opencli_baidu_netdisk_template.py --check
```

Use persistent OpenCLI session `site:baidu-netdisk`. The repository wrapper
owns source path/SHA/size validation, the append-only durable claim, uncertain-
side-effect handling, and authoritative cloud readback. The adapter owns exact
folder binding, credentialed paginated `/api/list`,
one claimed file-input attachment, and its low-level receipt. Never replace the
pair with a click macro or hard-coded profile/path.

An adapter `upload_submitted` result proves only one claimed input attachment;
it is not cloud completion. Record `video_ready` only after a later complete
folder scan returns exactly one matching basename. A target already present is
an idempotent success. More than one match, an incomplete scan, a wrong folder,
source mutation, or receipt identity mismatch fails closed.

Inspect-only `surfaceState.targetUiRows` also exposes the exact transfer row's
class/text and percentage widths. These are progress diagnostics, not cloud
receipts; compare the same claim/target across observations before calling it stalled.
Its bounded `rowControls` reports visible control labels/classes in that exact
row for diagnosis only; it never clicks them or authorizes a retry or resubmission.

For an explicitly authorized repair of a retained, running upload that stays
at zero progress, use `observe_stalled_upload` to persist its actual adapter
readback, then `repair_stalled_upload(..., repair_authorized=True)`. The service
requires another same-target zero-progress readback at least five minutes later,
unchanged local hash/size, a complete singleton target queue, zero cloud matches,
and the visible running transfer's pause control. It durably claims one recovery
before the adapter pauses that row, verifies its paused continue control, continues
that same row once and verifies running state. It never navigates, attaches a
file, cancels, reconstructs an uploader or changes the original upload claim.
This recovery is not called by ordinary sweeps. A consumed claim, uncertain
pause/continue result, user-paused row, progress, changed source or ambiguous
queue prohibits retry. Running readback is not cloud acceptance; keep the same
PTY through the original upload's exact cloud receipt and Handoff.

If this recovery returned without a final receipt and the original transfer is
now authoritatively paused, `continue_claimed_stalled_upload(...,
repair_authorized=True)` may finish that existing claim once after an explicit
repair. It requires an observed original command exit as well as the original
recovery claim, no success/continuation claim,
the exact singleton paused target at zero progress, a visible `继续上传|继续|开始`
control, zero cloud matches and unchanged local hash/size. It durably claims
only the continue action before dispatch, never pauses again or reattaches.
Its uncertain result consumes that continuation; no further retry is allowed.
An in-flight/unknown original dispatcher cannot be continued. For a legacy
attempt without an exit record, record only the actual completed command's
tool readback with `record_stalled_upload_dispatch_exit`; preserve unknown
historical pause/continue phases and never infer an exit from a paused row.

After an adapter upload claim, ordinary `advance_opencli` polling uses that
same adapter with `--inspect-only true`. It retains the exact uploader and
checks the original claim/folder/name without navigation or file attachment.
Do not switch to the independently leased `browser` surface to poll its queue
or repeatedly open the folder; an absent cloud row remains pending, never
permission to resubmit.
Transient transport/time-out failure in this inspect-only poll is persisted as
`netdisk_upload_readback_pending` and follows the same claim in the retained PTY.
It is not a failed attachment or permission to retry upload. Authentication,
authorization, malformed or mismatched readback still fails closed.

Baidu may clear `input.files` synchronously in its upload handler. The adapter
therefore captures the attached basename during the input/change capture phase
before the page consumes it; do not require a later non-empty `input.files`.
If a command fails after a durable claim, assume the side effect is uncertain:
reconcile the exact target and transfer UI, never attach the file again. A later
exact match completes the original claim without resubmission.

The adapter selects its exact site page, then performs one native click on the
visible file-name header to establish browser user activation before attaching
the file. A `--window foreground` flag alone does not prove activation. Its
`--activate-only true` probe attaches no file; it cannot prove upload completion.
Never replace the adapter with direct debugger calls or a synthetic DOM click.

## Exact local upload SOP (macOS / Microsoft Edge)

Do not manually decompose these stages into browser clicks. The repository
adapter performs them in order. `browser site:baidu-netdisk` and the upload
adapter use **different OpenCLI surfaces**, despite the identical session name;
the browser command's empty queue or healthy page is not uploader evidence.

| Step | Exact action / required result | Failure boundary |
|---|---|---|
| U1 | Bind the existing Netdisk job, exact basename, bytes and SHA from its ledger; verify the installed template using the commands above. | No new job, renamed copy, or full `capture-local` rerun. |
| U2 | Adapter `page.tabs()` finds exactly one page for the exact destination directory; `page.selectTab(page)` reuses it. | Multiple matches stop. `--inspect-only true` must never navigate or recreate a missing uploader. |
| U3 | Read the bound page's visibility and URL. If hidden, mark only that retained page with a random temporary title; the fixed native helper matches exact URL + title, foregrounds once, then restores the title in finally. Geometry is not identity: duplicate URLs and stale background bounds are expected. | Missing/ambiguous native match stops attachment and triggers Agent-owned diagnosis and same-job repair; it does not end the task. Never activate every window, refresh, close, or change browser settings. |
| U4 | Require the same page's 100 ms event-loop probe to finish; then credentialed paginated `/api/list` must prove exact folder, `errno=0`, complete scan, and 0 or 1 exact basename. Inspection changes no ads, styles or file inputs. | A synchronous read, `selected=true`, or `--window foreground` alone is not readiness. Use the emitted stage diagnostic; do not turn a timeout hint into a claim that a native dialog exists. |
| U5 | For a new prepared claim: persist claim, verify media hash/size, mark one file input, native-click the exact filename header, require user activation, attach once and bind its receipt. Existing claims follow only the recovery APIs below. | From `attach.begin` onward, absent receipt means uncertain effect, never permission to retry. |
| U6 | Keep the same item PTY running until later exact cloud readback yields `video_ready`; feed the exact LiangHui operation/receipt as specified by the local entry. | Attachment is not cloud completion; mailbox creation is `Handoff完成`, not remote `全部完成`. |

For diagnosis only, run the adapter with the existing ledger values and
`--inspect-only true --timeout 25 --site-session persistent --keep-tab true
--window foreground --format json`. Never omit `--inspect-only true` when
diagnosing an already-claimed upload. Use the wrapper, not a standalone adapter
invocation, for any actual attachment. Stages are emitted on stderr as compact
`xiaocao_upload_stage` JSON bound to `claimId`; stdout remains the receipt.
`--timeout` is an explicit adapter argument so transport and runtime deadlines
agree. Historical generic failures remain generic; a new reproduction cannot
retroactively prove an old attempt never attached a file.

The foreground helper is a bounded macOS **Edge window-management** operation,
not webpage scripting, file attachment, or a WeChat operation. It does not
modify extension permissions or browser security settings. An explicit security
denial, authentication/consent challenge, or unknown upload effect still stops
the corresponding action; do not switch surfaces to bypass it.

For a ledger-bound `upload_navigate_failed` / `upload_navigate`,
`upload_foreground_failed` / `upload_foreground` or
`upload_event_loop_failed` / `upload_event_loop` diagnostic,
the original run proves attachment was not reached. After repairing the adapter,
`resume_pre_attachment_upload` requires same-claim adapter folder/name readback
and no target in receipt/UI/inputs, then persists one continuation claim.
A navigation failure may continue only after the retained adapter page exists
and passes its exact-folder inspection; a missing page is not permission to
navigate or recreate an uploader during reconciliation. Never
infer this eligibility from a later inspection or a generic historical failure.

A claim-bound `upload_folder_scan_failed` / `upload_folder_scan` also proves
the adapter stopped before attachment. `resume_pre_attachment_upload` requires
a fresh complete exact-folder scan, same claim/name, zero cloud matches, and no
target in receipt, inputs, transfer text or rows. A collapsed queue alone is not
an uncertain submission for this proven pre-attachment stage. Its separate
`upload_folder_scan_repair_claimed_at` is consumed once, preserves any previous
reconciliation claim, and cannot become a periodic retry loop. Explicit
authentication or security-policy errors are not transport errors and never
qualify; recover normal authentication under the Edge reference instead.

Claimed-upload polling exposes a fresh `upload_observation` with safe queue
state/progress/time in the retained wait. A failed/paused exact row is
Agent-owned transport diagnosis, not ordinary healthy progress. Keep reading
the same uploader; provider state can change without an Agent action, and stale
error text can remain while its current class/progress shows uploading. Missing,
incomplete or conflicting queue evidence is `unknown`, never a retry permit.
These observations do not alter the claim, attach files or prove cloud success.

For the exact `file_chooser_not_opened` / `upload_before_attachment` failure,
OpenCLI's chooser timeout occurs before file assignment. After a verified repair,
`NetdiskEnrichmentService.resume_pre_attachment_upload` reconciles the same target
and permits one durably claimed continuation on the same job. The normal sweep
never invokes this repair. Unknown errors, prior submission, or a consumed repair
claim remain fail-closed. Do not relabel a historical generic failure without its
actual diagnostic evidence. Local-file access denial is a separate permission
gate: get explicit user approval before changing the extension's file-URL access.
After the user explicitly restores that permission, the same narrow API accepts
`file_access_restored=True` once for the existing permission-failed claim.

For an explicitly authorized repair of an older generic failed upload,
`resume_reconciled_failed_upload(..., repair_authorized=True)` is separate from
the normal sweep. It requires the original persistent uploader to remain intact,
at least five minutes since failure, a complete cloud scan with zero exact
matches, a fully rendered upload queue containing a successful control upload,
and no target in that queue, the attachment receipt, file inputs, or target UI
rows. It records the complete reconciliation proof and one repair claim before
submission. A lost/reloaded uploader, virtualized or incomplete queue, prior
submission, or consumed repair remains uncertain; never relabel those as an
observed chooser failure or use this API as a periodic retry loop.

Recover a closed/unresponsive tab under
[opencli-edge-recovery.md](opencli-edge-recovery.md). Authentication,
consent, or CAPTCHA remains a user-action gate. Upload stays local/transfer-only;
the remote capsule contains no source-video bytes or local path.
