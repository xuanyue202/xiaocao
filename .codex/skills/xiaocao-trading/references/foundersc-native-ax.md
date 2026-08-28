# Founder Securities native AX helper

Use this branch for the macOS Founder Securities 6.12 native helper under
`native/foundersc_ax_executor/`.

## Commands

Run from the Xiaocao repository root:

```bash
PYTHONPATH=src python3 scripts/foundersc_native_ax.py remote-bootstrap
PYTHONPATH=src python3 scripts/foundersc_native_ax.py build
PYTHONPATH=src python3 scripts/foundersc_native_ax.py version
PYTHONPATH=src python3 scripts/foundersc_native_ax.py preflight
PYTHONPATH=src python3 scripts/foundersc_native_ax.py probe
```

On a freshly pulled local or remote checkout, always start with
`remote-bootstrap --table-audit`. It is credential-free and UI-read-only: it
builds the source-hash-pinned helper and returns Git/runtime-source cleanliness,
source digest, app/Accessibility/screen/surface state, Keychain metadata, and
one `guidance.next_action`. Exit 0 only means the JSON receipt was produced;
read `guidance.status` and `guidance.next_action` before acting.

## Mandatory Agent state machine

After every permitted action, rerun `remote-bootstrap`; never chain remembered
steps from an earlier receipt.

| Next action | Agent rule |
|---|---|
| `review_runtime_source_changes` | Stop and report. Preserve all WIP; never reset/clean it or claim SHA provenance. |
| `unlock_macos`, `restore_verifiable_macos_login_state` | Human blocker. Never access Keychain or inject a password. |
| `launch_foundersc` | Run the returned fixed-bundle command once, wait for a stable window, rerun bootstrap. |
| `grant_accessibility_to_codex_or_terminal` | Human blocker; rerun after the permission is granted. |
| `configure_trade_keychain` | Human interactive TTY only; do not run in Automation or transfer the item. |
| `fill_login_password_then_solve_captcha` | Requires current user authorization. Run the returned fill once, then fresh screenshot -> exactly four digits -> field readback -> one login press. Only an explicit transport timeout gets one retry. |
| `unlock_trade_once` | Requires current user authorization. Run the returned command once. Unknown, mismatch, or `unlock_unproven` never retries. |
| `open_ordinary_trade_surface_then_reprobe` | Navigate without touching code/price/quantity/submit controls, then rerun. |
| `none` | Foundation ready only. Do not infer prepare/submit authority; OpenCLI still owns reconciliation. |
| `inspect_native_receipt` | Stop on unknown/incomplete state; preserve the receipt and do not improvise clicks. |

Manual password assistance is `focus-unlock`. It only raises the app and
focuses the unique secure field; the user types and confirms.

An app restart is a distinct `client_login_required` state. The explicit
`fill-login-keychain --acknowledge-local-password-fill` path may fill only the
Keychain-backed trade password and focus the unique CAPTCHA field. It must
never press `登录`; CAPTCHA stays in the slow recovery plane and unattended
recovery remains unproven.

Codex visual recognition may handle CAPTCHA in this slow recovery path when the
user authorizes it. Require a fresh screenshot, exactly four recognized digits,
field readback, and one login press. Permit at most one retry for an explicit
transport timeout; never loop on password/CAPTCHA or unknown outcomes. This
agent-assisted recovery is outside the millisecond order hot path.

`unlock-keychain --acknowledge-local-passguard-input` is an explicit
single-attempt local capability. It may read only the fixed
`xiaocao.foundersc.quant.trade` item, pass the secret on stdin, bind the page to
the masked Keychain account, and press the unique unlock confirmation once. A
custom-drawn confirmation may use only the helper's bounded
secure-field-relative coordinate guard and still requires semantic trade-ready
readback. It
must never print, log, persist, return, place in argv, or place in environment
the raw account/password. `unlock_unproven` is terminal for that attempt and
must not be retried automatically.

Treat `screen_locked` as a machine-state blocker distinct from the broker's
`authentication_required`. An unavailable lock-state readback is fail-closed.
Never inject the trade password while macOS itself is locked.

Provisioning is human-only through
`scripts/configure_foundersc_trade_keychain.py`; never run that command from an
Automation or without the user's action-time approval.

## Current contract

The helper is not a `BrokerAdapter` and exposes no order preparation, submit,
cancel, or replacement. Its receipts must keep `prepare=false`, `submit=false`,
and `unattended_recovery_proven=false`. Native holdings values are not AX
readable, so OpenCLI remains the assets/orders/deals reconciliation authority.

Do not infer capital permission from app unlock. Any future submit remains
owned by `trading_execution.py`, requires persisted intent/durable claim,
`safety.py`'s two real-capital conditions, exact field readback, one final
click, and OpenCLI reconciliation. UNKNOWN never retries.

For `MacBook-Pro-6.local`, use the registered Codex Remote project at
`/Users/xuanyue202/Documents/project/xiaocao`, pull with `git pull --ff-only`,
then run `remote-bootstrap --table-audit`. Keychain and Accessibility state are
machine-local and are never transferred through Git. A green Remote device is
not runtime readiness; only the fresh bootstrap readback is.

Full operator/design documentation: `docs/FOUNDER_NATIVE_AX.md`.
