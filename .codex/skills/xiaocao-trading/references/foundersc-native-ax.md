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
| `none` | Helper foundation is ready. The live runner must still prove native positions/orders/trades, the account-bound funds summary embedded in the positions capture, and order-page capabilities before `supports_submit=true`. |
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

`FounderscNativeAXBrokerAdapter` is the active App-only Book-B route. The Swift
helper is still a bounded transport, not an independent capital authority. It
provides:

- exact AX code/price/quantity set and readback, with a unique submit control;
- one Return from the exact quantity field, followed by one focused-dialog
  native `确定/确认` action; never repeated Return/Y retries;
- exact submit/cancel success-popup acknowledgment and broker order-id parsing;
- local macOS Vision OCR for positions, today orders and today trades, with
  account-bound funds values read from the same `资金股份` positions capture;
- full-query and buy/sell surface navigation bound to one masked fund account;
- exact-row cancellation with unique checkbox visual-delta proof and one
  cancel/confirm action; when the side token alone is low-confidence, the exact
  order-id/code/price/quantity tuple plus a unique two-character `入`/`出`
  suffix may provide the bounded side proof recorded in the receipt.

OpenCLI trading/view is sunset. The native route must not import, construct,
authenticate, query or reconcile through OpenCLI. `supports_submit=true` is
dynamic and requires helper version 8 or
newer, one unlocked account-bound App, the three native row-query surfaces,
the `资产/股票市值/余额/可用/可取` summary from that same positions capture,
`余额+股票市值=资产`, `0<=可取<=可用<=余额`, exact prepare and submit
capabilities, and local reconciliation capability. The separate `资金明细` tab
is diagnostic only and must not gate submission.

Native quantities must be exact positive integers. BUY remains restricted to
100-share board lots; SELL may use the exact broker-proved owned-lot remainder,
including a sub-100-share odd lot, and may never round or truncate it. Across
partial fills and a controlled replacement, `ExecutionReceipt.fill_price` is
the plan-level cumulative VWAP. Ownership evidence records each delta from the
difference in cumulative fill notional; a conclusive CANCELLED receipt with a
new positive cumulative fill is therefore still an ownership write. If that
local write fails after a terminal broker receipt, replay may repair only the
idempotent ownership row and must not query, cancel, or submit at the broker.

OCR validation is structural, not a two-identical-frame vote. Each capture must
prove the expected table headers, row geometry and exact critical numeric
shapes. Stock names are non-authoritative. Before submit, persist the complete
set of visible order ids and require zero pre-existing exact
`code+side+price+quantity` matches. After the one click, accept only one new
exact tuple with a new numeric order id; bind trades by
`order_id+code+side`, enforce cumulative fill `<= requested`, and map broker
status explicitly. Malformed/ambiguous fields or an unknown status become
UNKNOWN with `retry_allowed=false`; take a targeted fresh read only when the
first parse is structurally invalid, never to manufacture agreement.
The only bounded today-orders fallback is on that second read: the low-
confidence critical-header set must be a non-empty subset of `成交数量` and
`状态说明`; every fill must be blank/zero; every status must map exactly to a
known working/cancelled/rejected state; and an independent today-trades query
must prove the per-order traded quantity is also zero. Persist the bounded
headers and mode in locator evidence. Baseline and post-submit/recovery modes
must use phase-separated fields so a later strict or bounded read cannot
overwrite the durable baseline proof. Any nonzero fill, unknown status, other
low-confidence field or cross-table mismatch remains fail-closed.
Persist the baseline order ids and durable claim id so a lost submit response
can recover across restart only from one exact new-row delta. Missing durable
context stays UNKNOWN/no-retry.
Normalize broker numeric cells by field and locale: a Vision decimal comma
such as `17,3900` is 17.3900, while grouping commas such as `54,528.94` must
remain grouping separators. Preserve a validated success-popup order id plus
the native action/result evidence even when the order grid has not refreshed.
Immediate self-heal may retry only native reads and exact reconciliation for
that same durable submit claim. Account/allocation/lifecycle reads use a
bounded whole-snapshot retry after transient parsing, time-evidence, strict
asset-equation, or cross-table failures. The retry never relaxes an invariant
and records `actions=native_readback_only`, attempt count, failure codes, and
whether recovery occurred. A retry may reset a sticky query surface through
ordinary order-surface navigation without populating any field; if the normal
five-minute trade lock appears mid-read, that reset may use the fixed Keychain
unlock once and records `surface_resets`. Structurally unproved read-only
navigation records `surface_reset_failure_codes` and leaves only the original
whole-snapshot read budget; it never authorizes another click. Account/date
mismatch and every broker write remain non-retryable; exhausted read recovery
fails closed. It must never repeat Return, confirmation or submit.
Persist a separate cancel claim before the one external cancel action. If that
process stops or the response is lost, the same order id becomes readback-only;
never issue another cancel click from the existing claim. Apart from the two
bounded proofs above, critical OCR cells below the confidence floor and
malformed side text fail closed after the single targeted reread. Every
post-click outcome must separately preserve helper status, the helper-reported
click fact, exact click proof, confirmation state and selection proof mode even
when final broker readback stays UNKNOWN.

Do not infer capital permission from app unlock or `supports_submit`. Submit
remains owned by `trading_execution.py`, requires persisted intent/durable
claim and both `safety.py` real-capital conditions immediately before the
single action. Exact cancellation is implemented; automatic replacement stays
disabled for this adapter. A client restart
with CAPTCHA remains the slow recovery plane and may require bounded visual
assistance; the normal five-minute trading lock is recovered once from the
fixed Keychain item.

For `MacBook-Pro-6.local`, use the registered Codex Remote project at
`/Users/xuanyue202/Documents/project/xiaocao`, pull with `git pull --ff-only`,
then run `remote-bootstrap --table-audit`. Keychain and Accessibility state are
machine-local and are never transferred through Git. A green Remote device is
not runtime readiness; only the fresh bootstrap readback is.

Full operator/design documentation: `docs/FOUNDER_NATIVE_AX.md`.
