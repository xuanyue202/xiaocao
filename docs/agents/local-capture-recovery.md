# Local KOL OpenCLI and Edge recovery

The local hourly KOL node is WeChat-first. After a Xiaocao replay is captured and inline-compressed, local Baidu Netdisk access is transfer-only: upload the exact validated media, publish the credential-free handoff capsule, and let the remote Mac remain the only post-handoff writer. Do not restore local Netdisk subscription scans, transcription, analysis, publication, notification, or Book writes as a fallback.

An `OpenCLI browser command timed out`, an unresponsive tab, or an absent browser window is not by itself a user blocker. Reconcile the exact capture ID, Netdisk job ID, and upload ledger first, then recover the existing OpenCLI session instead of abandoning the run:

1. Query the existing session with `npx --yes @jackwener/opencli@1.8.6 browser <session> state` (the repository falls back to this pinned package when no global `opencli` exists).
2. If Microsoft Edge is not running or the session has no responsive foreground tab, launch Edge with `open -a "Microsoft Edge" "<target_url>"`, then bring the same session to the target URL with `opencli browser <session> open <url> --window foreground` and read `state` again. Edge is the only browser recovery target; reuse the existing session and Netdisk job.
3. If the session is on a login page, open the login panel and keep the job at `prepared`; request only the irreducible user authentication/phone confirmation. Do not treat a transient redirect through `/disk/main` as authenticated: require the target folder to remain bound and a credentialed `/api/list` readback with `errno=0` before continuing the same job automatically.
4. Retry an upload only when the ledger proves there is no upload claim. If a claim or `upload_started_at` exists without a conclusive receipt, treat the side effect as uncertain and reconcile the exact target row before retrying.

Do not stop merely because Edge was closed: launch/rebind it, read back the same OpenCLI session, and continue. Report a user-action blocker only when the recovered foreground page requires authentication, consent, CAPTCHA, or another action the agent cannot safely perform.
