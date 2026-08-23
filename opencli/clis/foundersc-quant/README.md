# Founder Securities OpenCLI templates

Template version: `5`
Site: `foundersc-quant`
Scope: secure persistent-session login, no-submit
probe/preparation/reconciliation/recovery, and verified mock/live environment
switching.

These templates are the browser-side adapter surface for the Xiaocao
`BookBLiveExecution.execute(plan, broker_adapter)` seam. They deliberately do
not expose a `submit` command in this phase. The route research result remains
`NO_ROUTE_PROVEN`; a page field or a successful navigation is not a broker
receipt.

Before running the commands, verify or explicitly install the versioned
templates from the repository:

```text
python3 scripts/install_opencli_foundersc_quant_template.py
python3 scripts/install_opencli_foundersc_quant_template.py --install
```

The first command is the default, read-only hash check. Only `--install`
writes the fixed template file set into `~/.opencli/clis/foundersc-quant`;
the installer does not read credentials or account configuration. The
installed `login` command is the only template command allowed to read a
credential: it reads the fixed `xiaocao.foundersc.quant.login` Keychain item
inside the OpenCLI process and never accepts or emits the account or password
as an argument, log field, receipt field, or exception message.

Run the repository preflight separately when Keychain readiness must be
checked. It emits only presence, length, match and access-status booleans; it
never prints account identifiers or password bytes:

```text
PYTHONPATH=src .venv/bin/python scripts/foundersc_keychain_preflight.py \
  --observed-login-fingerprint '123******789' \
  --observed-trade-fingerprint '987******210'

PYTHONPATH=src .venv/bin/python scripts/foundersc_keychain_preflight.py \
  --observed-login-fingerprint '123******789' \
  --observed-trade-fingerprint '987******210' --read-secrets
```

The secret-read mode is bounded by a timeout and reports
`timeout_or_acl_prompt` when macOS requires interactive Keychain consent. Do
not place that mode in unattended morning automation until it returns
`readable` for both fixed services.

## Commands

```text
opencli foundersc-quant login -f json

opencli foundersc-quant probe \
  --expected-environment mock \
  --logical-account-id primary \
  -f json

opencli foundersc-quant environment \
  --target live --expected-current mock \
  --logical-account-id primary \
  -f json

opencli foundersc-quant prepare \
  --route manual-limit \
  --expected-environment mock \
  --logical-account-id primary \
  --code 600000 --side buy --quantity 100 --price 10.00 \
  -f json

opencli foundersc-quant reconcile \
  --scope all --expected-environment mock \
  --logical-account-id primary -f json

opencli foundersc-quant recover \
  --route assets --expected-environment mock \
  --logical-account-id primary -f json
```

`login` visits the persistent session and accepts an existing session only
when it proves an authenticated mock baseline: UI label, mock request namespace
and the authenticated fund-account readback must all agree. Otherwise it fills
the unique phone/password controls from the fixed Keychain item and clicks the
unique `登录模拟盘` control. It then requires the same safe mock proof. CAPTCHA,
SMS, ambiguous controls or a failed readback return `auth_required` or
`unknown`; the command does not retry a login.

`prepare` supports `manual-limit`, `opening-auction`, and `timed-order`.
Manual limit never clicks `买入` or `卖出`; because the observed page does not
prove a separate non-submitting side selector, `prepare --route manual-limit`
reports a capability gap instead of claiming the requested side was selected.
Opening auction opens the form, fills only the requested fields, reads them
back, and closes the empty form with its exact `取消` control. Timed order must
first prove that the requested numeric limit is one native price option. The
observed timed-order widget instead offers quote-derived values such as
`现价`, `买一`, `卖一`, and `开盘价`; writing a decimal into its inner input does
not select the Angular model. In that shape `prepare --route timed-order`
returns `timed_order_numeric_limit_not_supported` and closes the form. These
read-only routes never click `保存`, `启动`, or `确定`.

`environment` changes only the unique mock/live switcher and then requires the
same tab to agree at two layers: the visible mock/live label and the most
recent environment-specific request namespace (`/qt/.../mock/...` versus the
live namespace). This catches an already-open tab whose in-memory UI did not
follow a shared local-storage change. It never logs in, reads credentials,
prepares a capital action, saves a strategy, or submits an order. Use a second
verified call with `--target mock --expected-current live` to restore the
sensor-safe default after an isolated live-page probe.

`FZZQ_QUANT_BASE_URL` may override the configured page root, but it is accepted
only when it remains the exact Founder Securities origin and path. Credentials,
passwords, Keychain values, cookies, local storage and security-control data
are not read or printed by any other command. The login password is used only
for the bounded login action and is never returned.

## Common JSON receipt

Every command returns one JSON receipt row. The stable broker-neutral fields
are:

```json
{
  "template_name": "foundersc-quant/reconcile",
  "template_version": 5,
  "status": "reconciled",
  "environment": "mock",
  "expected_environment": "mock",
  "logical_account_id": "primary",
  "account_binding": "not_proven",
  "fund_account_fingerprint": "123******789",
  "route": "#/home/myAccount/query",
  "order_id": null,
  "strategy_id": null,
  "task_id": null,
  "requested_shares": null,
  "filled_shares": null,
  "remaining_shares": null,
  "order_price": null,
  "fill_price": null,
  "latest_price": null,
  "active": null,
  "status_reason": "page_readback_completed",
  "error_code": null,
  "observed_at": "2026-08-15T00:00:00.000Z",
  "submitted_at": null,
  "cancelled_at": null,
  "retry_allowed": null,
  "field_readback": {},
  "submitted": false,
  "saved": false,
  "started": false,
  "cancelled": false,
  "reconcile_required": false,
  "reconcile_complete": true,
  "submit_capability": false,
  "locator_proof": {},
  "capabilities": {"submit": false}
}
```

The broker identifiers and fill quantities remain `null` when the current
page has no actual row or the visible table does not expose the identifier.
`field_readback` contains only the requested form fields and sanitized page
facts. It does not infer a fill, order id, status mapping, basket rule,
T+1 ownership, or retry permission. In particular, `filled_shares` and
`remaining_shares` are `null` in this phase: no page contract currently
proves whether a displayed fill value would be cumulative for one order or
an aggregate across orders. `observed_at` is the local template readback
time, not a broker event timestamp.

`reconcile` includes account assets, query orders/deals, active strategy
surfaces, and—when the app exposes exactly one same-origin opaque link—the
manual order/deal page and its read-only withdraw-control count. It walks
bounded pagination and virtual-scroll surfaces, requiring a unique next
control or a proven terminal scroll position before a surface is complete.
It reports `reconciled` only when every requested surface has a complete
visible scan, the route is still bound, and the page has proven the target
account binding.
If a table is paginated, virtualized, missing, its tab cannot be read, or the
opaque manual route is not unique, it
returns `reconciled_partial`, `reconcile_complete=false`, and
`reconcile_required=true`; this is not a conclusive broker outcome.

Template v5 also exposes a strict `allocation_summary` from either one unique
asset-summary card set or one unique table row containing `总资产`, `证券市值`,
and `可用资金`. Ambiguous/missing labels or disagreeing sources keep the summary
incomplete. The page-side `fund_account_fingerprint` is masked; Xiaocao compares
it in-process with the separately read Keychain trade-account metadata and
persists only a hash of that binding. Neither mixed-account total assets nor
total securities market value becomes the Book-B settled-NAV basis.
When the visible asset page omits the label, the fingerprint comes from the
platform's authenticated, same-origin, read-only `/qt/user/getBaseInfo`
response. The browser template masks the numeric account before returning from
page context; the raw account never enters OpenCLI output, logs, arguments, or
evidence.

## Failure and recovery contract

- Read-only commands return `status=auth_required` on a login/security-control
  page. The explicit `login` command alone may fill the Keychain-backed login
  password; CAPTCHA, SMS or an unproven post-login state still stops for the
  user.
- A correctly identified environment without a proven fund-account binding
  returns `status=unknown` from `probe` with
  `status_reason=account_fingerprint_not_proven`; it is not readiness for a
  write.
- `prepare` compares every requested code, side, quantity, price, date and
  trigger-time field with the actual page readback. A mismatch is a
  `capability_gap`; a matching form is still not submit-ready unless the
  account binding is proven.
- A visible environment label whose request namespace belongs to the other
  environment returns `environment_ui_data_namespace_mismatch`; no prepare or
  switch receipt may treat that tab as ready.
- A non-unique environment container, route shell, or required field returns
  `status=unknown` or `status=capability_gap` with `reconcile_required=true`
  where the page state may be ambiguous.
- Navigation, evaluate, loading-shell and transition failures return
  `status=unknown`; callers must reconcile before any later write operation.
- `environment_mismatch` is a clean precondition failure, not a retryable
  browser error.
- There is no submit or withdraw action in this version. `cancelled` remains
  false for a form that was merely closed; `form_closed` in the readback means
  the empty preparation dialog was closed locally, not that a broker order was
  cancelled.

## Known evidence gaps

The templates preserve the research gaps rather than hiding them:

- The page parser requires exactly one numeric fund account from either the
  exact visible `资金账号` label or the authenticated same-origin base-info
  response. If that masked fingerprint does not match the Keychain
  trade-account metadata, `logical_account_id=primary` remains unproven and
  live allocation facts are not emitted.
- The current runtime has not proven a stable strategy/order/deal receipt
  chain, quantization cancellation finality, mixed-account ownership, T+1
  semantics, or authoritative market-state timestamps.
- The manual order route contains an opaque account segment. If the page does
  not expose exactly one same-origin link to that route, the adapter records
  the manual surface as unavailable; `can_withdraw` remains `null` because no
  row-level cancellation fact has been proven.
- The opening-auction route does not natively express
  `min(frozen_open * 1.005, basket_price)`.
- The timed-order route has a native create/start/stop lifecycle in mock, but
  its quote-derived price selector cannot express that numeric limit either.
  `开盘价` at 09:30 is only an experiment approximation: it omits the 0.5%
  tolerance and basket abandon cap. A pricing condition is also not equivalent
  because it waits for a threshold crossing before sending a quote-relative
  order.
- Price-segment and time-segment algorithms also use a numeric entry trigger
  followed by the same quote-derived price selector, then intentionally emit
  repeated child orders by price or time interval. They change both trigger
  and slicing semantics, so they cannot substitute for Book B's one-shot
  bounded limit order. TWAP, VWAP, iceberg and combination algorithms remain
  separate execution policies rather than fallback routes.
- Pagination/virtual-scroll scans are bounded at 100 pages/steps and remain
  incomplete when the page exposes an ambiguous control or fails to reach a
  terminal boundary.
- The mock manual-limit route has previously redirected to the account page;
  that route is reported as a capability gap rather than being treated as a
  successful form.
