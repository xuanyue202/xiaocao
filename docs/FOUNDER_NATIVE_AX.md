# Founder Securities 6.12 native AX executor foundation

Status: **bounded native foundation; not a production submit route**.

This component turns the locally installed macOS Founder Securities client into
a versioned deterministic capability surface. Source is synchronized through
Git; every Mac builds the helper locally from the same source digest. No user
home path, account, password, compiled binary, Accessibility decision, or
runtime receipt is committed.

## Current boundary

Implemented:

- bounded application/window/surface probe;
- locked-vs-trade-ready classification;
- semantic discovery of the buy/sell submit control and editable field count;
- holdings table shape audit without emitting account values;
- manual unlock assistance by raising the window and focusing the unique secure
  field;
- initial-client-login assistance that fills only the Keychain-backed trade
  password and focuses CAPTCHA without pressing login;
- explicitly enabled, single-attempt Keychain-backed password injection with
  masked account binding and semantic trade-ready readback.

Not implemented or authorized:

- setting order code, price, or quantity;
- clicking buy/sell submit;
- cancellation or replacement;
- reading native holdings cell values (the current client exposes cell geometry
  but not their text through AX);
- replacing OpenCLI assets/orders/deals reconciliation;
- claiming `unattended_recovery_proven=true`.

The helper always reports `prepare=false`, `submit=false`, and
`unattended_recovery_proven=false`. A successful password unlock proves only
that one local unlock attempt reached a semantic trade surface. It grants no
capital authority.

## Build and probe

From the repository root on each Mac:

```bash
PYTHONPATH=src python3 scripts/foundersc_native_ax.py remote-bootstrap
PYTHONPATH=src python3 scripts/foundersc_native_ax.py build
PYTHONPATH=src python3 scripts/foundersc_native_ax.py version
PYTHONPATH=src python3 scripts/foundersc_native_ax.py preflight
PYTHONPATH=src python3 scripts/foundersc_native_ax.py probe
```

`remote-bootstrap` is the canonical first command after a remote Mac pulls the
reviewed commit. It builds or reuses the source-hash-pinned helper, performs a
read-only native probe, reads only Keychain metadata, verifies the Git SHA and
whether the runtime source scope is clean, and emits one JSON `guidance` next
action. It never reads a Keychain secret and never mutates the broker UI.
Expected states such as `action_required`, `limited`, and `blocked` are emitted
as data; an Agent must interpret the JSON rather than treating process exit 0
as readiness.

The build is cached under
`output/.cache/foundersc_native_ax/bin/<source-sha256>/`. Callers use that
source-hash-pinned path rather than SwiftPM's private layout. A source update
therefore cannot silently reuse an old binary.

The helper never requests Accessibility permission. If the receipt says
`accessibility_denied`, grant the existing Codex/terminal runtime Accessibility
access on that Mac and rerun the read-only probe.

`screen_locked` is a separate machine-state result. It must not be reported as
an application failure and no password injection is attempted until the user
has unlocked the macOS login session.
`screen_lock_state_unavailable` is also fail-closed and permits no UI action.
Keychain metadata inspection is deferred in both states to avoid reporting an
inaccessible login Keychain as a missing item.

## Friendly password input

The recommended first path is manual input with deterministic assistance:

```bash
PYTHONPATH=src python3 scripts/foundersc_native_ax.py focus-unlock
```

This raises the Founder window and focuses the one proven secure field. The user
types the trade password and confirms in the app.

After an app restart, Founder 6.12 presents a separate client-login surface
with a CAPTCHA. The helper classifies it as `client_login_required`; one
explicit command fills only the trade password and focuses CAPTCHA:

```bash
PYTHONPATH=src python3 scripts/foundersc_native_ax.py \
  fill-login-keychain --acknowledge-local-password-fill
```

The helper never presses `登录`; CAPTCHA must be completed before one login
submission. This is intentionally not unattended recovery and is distinct from
the later in-session trade unlock.

CAPTCHA recognition is allowed to use the Codex visual/computer-control slow
path: take a fresh screenshot, accept only four digits, fill the CAPTCHA field,
read the value back, and press `登录` once. A clearly classified transport error
such as `接收行情主站信息超时` may receive one bounded retry; password/CAPTCHA
errors and unknown results do not loop. This recovery plane has no millisecond
latency requirement and never enters the order hot path.

For a machine whose fixed Keychain item has already been provisioned and whose
ACL is accepted, one explicit local unlock attempt is available:

```bash
PYTHONPATH=src python3 scripts/foundersc_native_ax.py \
  unlock-keychain --acknowledge-local-passguard-input
```

The password is read only from service `xiaocao.foundersc.quant.trade`, passed
to the helper on stdin, and never decoded for receipts or placed in argv,
environment variables, logs, or files. Before setting the secure field, the
helper requires exactly one locked field, exactly one page account fingerprint,
an exact match with Keychain metadata, and either one semantic confirmation or
a tightly bounded point derived from the proven secure-field and window
geometry. The current `确定` control is custom-drawn, so the guarded-coordinate
branch is expected on 6.12. It clicks that point at most once. Missing readback
becomes `unlock_unproven`; callers
must not retry automatically.

Provisioning or replacing the fixed item is a separate human-only operation:

```bash
PYTHONPATH=src python3 scripts/configure_foundersc_trade_keychain.py
```

That command requires an interactive terminal and explicit phrase, uses hidden
account/password prompts, refuses to overwrite a different fixed account, and
does not enable real capital or mint an authorization.

## Remote Mac reuse

For `MacBook-Pro-6.local`, use the registered Codex Remote Xiaocao project and
its repository at `/Users/xuanyue202/Documents/project/xiaocao`:

```bash
git pull --ff-only
PYTHONPATH=src python3 scripts/foundersc_native_ax.py \
  remote-bootstrap --table-audit
```

The second command is the complete machine-local bootstrap readback. Its JSON
contains the Git SHA, broad worktree cleanliness, runtime-source cleanliness,
native source digest, helper build receipt, app/Accessibility/screen/surface
state, credential-free Keychain metadata, and exactly one bounded next action.
The Agent follows this state machine and reruns `remote-bootstrap` after every
action:

| `guidance.next_action` | Owner | Required behavior |
|---|---|---|
| `review_runtime_source_changes` | human | Stop and report; preserve the worktree. Never reset, clean, or claim the checked-out SHA is the running source. |
| `unlock_macos` / `restore_verifiable_macos_login_state` | human | Restore the macOS login session, then rerun. Never inject a broker password while the machine session is locked or unverifiable. |
| `launch_foundersc` | Agent | Run the returned fixed-bundle command once, wait for a stable window, then rerun. |
| `grant_accessibility_to_codex_or_terminal` | human | Grant the already-running Codex/terminal runtime Accessibility permission, then rerun. |
| `configure_trade_keychain` | human | Run the returned interactive configurator in that Mac's TTY. Never transfer a Keychain item or secret through Git, chat, env, argv, or a file. |
| `fill_login_password_then_solve_captcha` | Agent with current user authorization | Run the returned explicit fill once; use a fresh screenshot for exactly four CAPTCHA digits, read the field back, press login once, and rerun. Only an explicit transport timeout permits one retry. |
| `unlock_trade_once` | Agent with current user authorization | Run the returned explicit unlock once and rerun. `unlock_unproven`, unknown output, or account mismatch is terminal for the attempt. |
| `open_ordinary_trade_surface_then_reprobe` | Agent | Open the ordinary trade page without touching code/price/quantity/submit controls, then rerun. |
| `none` | Agent | Native readiness/unlock foundation is ready. This is not order authority; use OpenCLI for account/assets/orders/deals reconciliation. |
| `inspect_native_receipt` | human | Unknown/incomplete state: stop, preserve evidence, and do not improvise UI clicks. |

If the remote app has restarted, validate `fill-login-keychain`, complete its
CAPTCHA locally, and only then validate the in-session unlock path.

Keychain state and Accessibility permission are machine-local and must never be
copied through Git or an ad-hoc filesystem transfer. Remote connectivity alone
does not prove this runtime readiness.

### Agent handoff contract

The remote Agent must start from `remote-bootstrap`, not from screenshots or
remembered coordinates. It may execute only the single state-matched action,
must read back a fresh bootstrap receipt afterward, and must stop on dirty
runtime source, unknown state, mismatched account, or unproven side effect.
Bootstrap and unlock do not authorize order preparation or submission. Native
holdings values remain unreadable through AX, so OpenCLI remains the
reconciliation authority even when `guidance.status=ready`.

## Local acceptance, 2026-08-28

- Initial client login: Keychain password fill succeeded, one four-digit
  CAPTCHA was visually recognized and read back, and one bounded retry
  recovered an explicit market-server timeout.
- Unlocked order surface: semantic buy form, three editable fields, one account
  fingerprint, and a 5×11 holdings table were observed; native cell values
  remained unreadable.
- In-session unlock: after an intentional `锁定交易`, the helper activated the
  app through the fixed bundle identifier, injected the Keychain password,
  clicked the guarded `确定` coordinate once through HID, and reached
  `trade_ready` in about 157 ms.
- No code/price/quantity field, buy/sell control, cancellation, or order submit
  was touched during acceptance.

## Promotion gate for order execution

Future native `prepare/submit` work must plug into
`src/xiaocao/live/trading_execution.py`, not expose an independent order CLI.
Before promotion it must prove at least:

- exact side/page postconditions despite the custom-drawn top tabs;
- exact code/price/quantity readback;
- persisted canonical intent before prepare;
- durable claim before the one final click;
- both `safety.py` real-capital conditions immediately before submit;
- same-account OpenCLI reconciliation and UNKNOWN/no-retry behavior;
- local and remote app-version acceptance without active-active writers.

Until all gates pass, native AX is only the fast readiness/unlock foundation.
