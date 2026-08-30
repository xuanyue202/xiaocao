# Founder Securities 6.12 native App executor

Status: **production-capable Book-B route, fail-closed**.

The active `native-app` route uses only the locally installed macOS Founder
Securities App. It does not compose with OpenCLI for login, environment,
assets, positions, orders, trades, prepare, submit, reconcile or recovery.
OpenCLI remains a separate legacy compatibility route.

## Architecture and authority

The implementation has three layers:

1. `native/foundersc_ax_executor/` is a source-hash-pinned Swift helper. It
   performs bounded Accessibility actions, captures only the Founder window and
   runs local macOS Vision OCR.
2. `FounderscNativeAXBrokerAdapter` validates account/query/order evidence and
   maps it to the broker-neutral receipt contract.
3. `TradingExecution` owns immutable intent, durable claims, exact-once state,
   writer fencing and the `safety.py` real-capital gate.

App unlock or `supports_submit=true` is capability evidence, not capital
authorization. A real submit still requires the existing Keychain-backed
capital toggle plus a valid scoped signed authorization immediately before the
single click.

## Implemented native capability

- Application, window, macOS lock, Accessibility and broker-surface state
  classification.
- One masked fund-account fingerprint with exact Keychain metadata binding.
- One-attempt in-session trade unlock using the fixed
  `xiaocao.foundersc.quant.trade` Keychain item over stdin.
- Buy/sell page navigation and exact mapping of code, price and quantity
  controls.
- Millisecond-scale field set, AX readback and optional clear without submit.
- One explicitly enabled submit action. The quantity field receives exactly
  one Return to open the broker confirmation. The focused dialog must expose
  one native `确定/确认` control and retain the exact prepared tuple. OCR may
  supplement marker/tuple evidence, but it never supplies the confirmation
  click target.
- Exact success-popup handling. `委托已提交,合同号是...` is parsed for one
  numeric order id and `撤单已提交!` is matched exactly before the popup's
  unique native confirm control is pressed once.
- Full-query native reads for positions, today orders, today trades and funds.
- Complete native allocation capsule from the positions summary plus row-level
  market values.
- Exact cancellation: zero all selections, identify one
  `order-id+code+side+price+quantity` row, prove that only its checkbox changed,
  click `撤单` once, confirm once, then reconcile that same order id.

Automatic replacement remains disabled in the native adapter. Unknown action
outcomes are reconciliation-only and never cause another Return, click or
submit.

## OCR and reconciliation contract

The helper captures only the Founder window with `CGWindowListCreateImage` and
uses `VNRecognizeTextRequest` locally with accurate recognition. Screenshots
and raw account values are not persisted or returned. Fund/shareholder account
cells are masked.

Two identical OCR frames are not an authority gate: they share the same pixels,
model and systematic failure modes. The accepted logic is:

1. One capture must prove the expected table headers, one table geometry and a
   complete row parse. A second targeted capture is permitted only when the
   first parse is structurally invalid.
2. Security code, side, price, quantity, order id, filled quantity and status
   are critical. They must pass exact shape/range checks; stock names are
   descriptive and may not authorize a match.
3. Before prepare, read all current order ids and require zero existing exact
   `code+side+price+quantity` matches.
4. After the one submit, require exactly one matching row whose numeric order
   id was absent from the baseline.
5. Match trades by `order_id+code+side`; cumulative fill must not exceed the
   requested quantity and must agree with the order row when both are nonzero.
6. Map known Chinese broker statuses explicitly. Malformed, duplicate,
   missing or unknown data returns UNKNOWN with `retry_allowed=false`.
7. Persist the complete pre-submit order-id baseline and durable claim id. If
   the submit response is lost across a process restart, recovery is allowed
   only when exactly one new exact tuple exists outside that durable baseline;
   legacy UNKNOWN rows without both facts remain UNKNOWN.
8. Require every non-empty token in a critical table cell to meet the local
   Vision confidence floor (`0.50`, calibrated against the real two-order
   Founder table). Side text is never typo-corrected for receipt or
   cancellation authority; a malformed side triggers one fresh read and then
   fails closed.

This is a before/after delta proof, not a fuzzy full-row comparison. It both
avoids false failures from harmless name OCR and prevents uncertain critical
numbers from becoming an order acknowledgment.

## Dynamic promotion gate

`BrokerCapability.supports_submit` is true only when all of these are proven in
the current process:

- helper version 8 or newer;
- App running, Accessibility trusted and macOS session unlocked;
- exactly one expected fund-account fingerprint;
- positions, today-orders, today-trades and funds query surfaces all parse;
- an ordinary buy/sell surface exposes exact prepare and submit capability;
- native reconciliation is available.

No hard-coded `supports_submit=False` remains in the native adapter. Probe
failure returns `ready=false`, `supports_submit=false` and no order action.

## Password and recovery boundary

The normal five-minute broker lock is `authentication_required`, distinct from
macOS `screen_locked`. When already authorized by the live runner, the former
may be recovered once from the fixed Keychain item; the latter is always a
human blocker. Password bytes never enter argv, environment, logs, receipts or
files.

An App restart presents `client_login_required` with CAPTCHA. The helper may
fill only the Keychain-backed password and focus CAPTCHA; it never presses
login automatically. CAPTCHA recognition is a slow, bounded visual recovery
path and is outside the order hot path.

Provisioning remains human-only:

```bash
PYTHONPATH=src python3 scripts/configure_foundersc_trade_keychain.py
```

The 09:20 Automation must never run that command or mint/rotate a capital
authorization.

## Build and diagnostics

From the repository root:

```bash
PYTHONPATH=src python3 scripts/foundersc_native_ax.py build
PYTHONPATH=src python3 scripts/foundersc_native_ax.py version
PYTHONPATH=src python3 scripts/foundersc_native_ax.py probe --table-audit
PYTHONPATH=src python3 scripts/foundersc_native_ax.py remote-bootstrap --table-audit
```

Build artifacts are cached under
`output/.cache/foundersc_native_ax/bin/<source-sha256>/`; compiled binaries and
runtime receipts are not committed. `remote-bootstrap` is credential-free and
read-only. It proves helper foundation only; the live runner must still perform
the full native broker probe before `supports_submit=true`.

## Local acceptance, 2026-08-30

- In-session Keychain unlock reached the same account-bound full-query surface.
- Positions parsed 5 rows. Their `最新市值` sum equaled the displayed
  `股票市值`.
- Allocation readback proved
  `可用 54459.32 + 股票市值 154835.40 = 资产 209294.72`.
- The user-created non-trading-day order parsed exactly as
  `515120 / 买入 / 0.6460 / 100 / 委托编号 6000002 / 未报 / 成交 0`.
- A baseline prepare for that same tuple was rejected before form entry because
  one exact order already existed.
- Five consecutive `000001 / BUY / 10.00 / 100` read-only prepare cycles all
  set, exactly read back and cleared the form with no submit. Warm end-to-end
  cycles were approximately 0.58–0.90 seconds; the bounded helper hot path is
  millisecond-scale.
- A full real-App adapter probe returned `ready=true`,
  `supports_submit=true`, `supports_reconcile=true`, `supports_cancel=true` and
  `opencli_used=false`.
- An authorized end-to-end test submitted
  `512010 / BUY / 0.3500 / 100`. The App returned contract/order id `6000005`;
  same-account today-orders readback found exactly that new tuple as `未报`.
- The cancellation probe uniquely selected and cleared only `6000005`. The
  one real cancel then returned `撤单已提交!`; final today-orders readback showed
  `6000005 / 已撤 / 成交数量 0`, while the pre-existing `6000002` remained
  `未报` and untouched during that action. A later separately authorized exact
  cancel of `6000002 / 515120 / BUY / 0.6460 / 100` returned the same broker
  success and independent readback proved `6000002 / 已撤` without replaying
  the already-terminal `6000005`.
- A repeated Return was deliberately rejected as an automation strategy. In
  the observed UI the first confirmation dialog left focus on the underlying
  quantity field, so another Return opened a second confirmation dialog. Both
  were safely cancelled and no order was created. Production code therefore
  sends one Return, then uses the focused dialog's unique native button.

The App may clear or reset fields after a completed submit, but that behavior
is not an exact-once authority: it occurs too late to protect the uncertain
interval between opening and resolving the confirmation dialog.

## Qbot/easytrader reference comparison

The implementation deliberately follows the proven part of
[Qbot easytrader](https://github.com/UFund-Me/Qbot/blob/main/qbot/engine/trade/easytrader/easytrader/clienttrader.py)
and its
[grid strategies](https://github.com/UFund-Me/Qbot/blob/main/qbot/engine/trade/easytrader/easytrader/grid_strategies.py):
bind one application/window, use native controls for fields and buttons, and
read broker tables structurally. Qbot's normal easytrader path uses Windows
`pywinauto` control ids, `set_edit_text/type_keys`, button `.click()`, and
clipboard grid copy. It does not OCR ordinary order or holdings tables. Its
`thsauto` path uses DdddOCR only for the anti-copy verification image; normal
tables are still copied from the clipboard.

The reusable ideas are native control ownership, exact row identity, shortcuts
only after client-specific proof, and clipboard/table extraction when the
client exposes it. Windows control ids and F-key mappings are not portable to
Founder macOS. Qbot
[`thsauto`](https://github.com/UFund-Me/Qbot/blob/main/qbot/engine/trade/trading/thsauto/thsauto.py)'s
loop that sends `Y` repeatedly when the result is
unknown is explicitly not adopted because it lacks a durable submit-delta
guard.

Our OCR engine is Apple's local Vision framework, not DdddOCR. Founder macOS
exposes AX table geometry but not readable cell values, so Vision fills a
different gap. Code, side, price, quantity, order id, fill quantity and status
stay exact, and low-confidence critical cell tokens invalidate the parse.
Codex screenshots can diagnose a disputed read, but cannot authorize or repair
a live receipt in the millisecond action path.

## Runtime command

The independent 09:20 Book-B task runs:

```bash
PYTHONPATH=src .venv/bin/python scripts/book_b_live_morning.py \
  --date today --route native-app
```

The native App has no mock namespace. Exit therefore records
`native_environment_restore_not_applicable`; it must never report a fabricated
switch to mock. Durable intent and reconciliation state remain under
`output/live/book_b_live_execution/`, isolated from all paper ledgers.
