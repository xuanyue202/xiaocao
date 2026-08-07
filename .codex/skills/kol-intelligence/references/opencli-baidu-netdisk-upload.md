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

Recover a closed/unresponsive tab under
[opencli-chrome-recovery.md](opencli-chrome-recovery.md). Authentication,
consent, or CAPTCHA remains a user-action gate. Upload stays local/transfer-only;
the remote capsule contains no source-video bytes or local path.
