# Founder Securities native AX helper

This macOS-only helper is the reusable native foundation for Founder Securities
6.12. It uses the system Accessibility API and emits one credential-safe JSON
receipt per invocation.

Current commands:

- `version`: helper/schema discovery.
- `probe [--table-audit]`: bounded read-only state and capability probe.
- `focus-unlock`: raises the locked trade page and focuses its unique secure
  field for manual input. It never confirms the form.
- `fill-client-login-stdin`: fills the initial client-login password and
  focuses the unique CAPTCHA field. It never presses the login button; CAPTCHA
  remains an explicit human recovery step.
- `unlock-stdin`: explicitly gated single-attempt password injection. The
  password is accepted only on stdin, never argv/environment, and only after a
  masked trade-account fingerprint matches the unique page account control.
  The client version's confirmation is custom-drawn, so the helper uses a
  tightly bounded secure-field-relative click only when its geometry matches
  the known locked surface; semantic trade-ready readback is still mandatory.
- `open-order-surface`, `prepare-order`, `submit-prepared-order`: account-bound
  deterministic order navigation, exact AX field set/readback, one Return to
  open confirmation and one focused native confirm action.
- `open-query-surface`, `read-query`: positions, orders, trades and funds using
  AX geometry plus local Vision OCR.
- `open-cancel-surface`, `probe-cancel-selection`, `cancel-order`: one exact
  numeric row selection proof and at most one cancel/confirmation action. The
  only OCR fallback is a receipt-labelled two-character `入`/`出` side suffix
  when order id, code, price and quantity are already exact and unique.
- `probe-pending-order-confirmation`, `confirm-pending-order`: recovery tools
  for one already-visible exact transaction confirmation; they never send a
  second Return.

The helper cannot authorize capital and is not a replacement for
`trading_execution.py` or `safety.py`. The active native route performs all
account, query, order and cancellation work in the Founder App; OpenCLI is a
separate legacy route and is never composed into native reconciliation.

Build and invoke it through `scripts/foundersc_native_ax.py`; do not depend on
SwiftPM's internal `.build` path. After a reviewed checkout is pulled onto a
new Mac, the canonical first command is:

```bash
PYTHONPATH=src python3 scripts/foundersc_native_ax.py remote-bootstrap --table-audit
```

That wrapper builds this helper, checks Git/source provenance, performs a
read-only probe and returns one bounded `guidance.next_action`; it does not
read a Keychain secret or mutate the broker UI.
