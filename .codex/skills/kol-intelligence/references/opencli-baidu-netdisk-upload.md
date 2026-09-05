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
folder navigation, credentialed paginated `/api/list`, semantic ad dismissal,
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
