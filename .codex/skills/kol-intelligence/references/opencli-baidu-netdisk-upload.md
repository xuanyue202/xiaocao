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

For a ledger-bound `upload_foreground_failed` / `upload_foreground` diagnostic,
the original run proves attachment was not reached. After repairing the adapter,
`resume_pre_attachment_upload` requires same-claim adapter folder/name readback
and no target in receipt/UI/inputs, then persists one continuation claim. Never
infer this eligibility from a later inspection or a generic historical failure.

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
