# Founder Securities OpenCLI templates

Template version: `2`
Site: `foundersc-quant`
Scope: read-only probe/recovery/reconciliation and no-submit form preparation.

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
the installer does not read credentials or account configuration.

## Commands

```text
opencli foundersc-quant probe \
  --expected-environment mock \
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

`prepare` supports `manual-limit`, `opening-auction`, and `timed-order`.
Manual limit never clicks `买入` or `卖出`; because the observed page does not
prove a separate non-submitting side selector, `prepare --route manual-limit`
reports a capability gap instead of claiming the requested side was selected.
Opening auction and timed order
open the form, fill only the requested fields, read them back, and close the
empty form with its exact `取消` control. They never click `保存`, `启动`, or
`确定`.

`FZZQ_QUANT_BASE_URL` may override the configured page root, but it is accepted
only when it remains the exact Founder Securities origin and path. Credentials,
passwords, Keychain values, cookies, local storage and security-control data
are not read or printed by these templates.

## Common JSON receipt

Every command returns one JSON receipt row. The stable broker-neutral fields
are:

```json
{
  "template_name": "foundersc-quant/reconcile",
  "template_version": 1,
  "status": "reconciled",
  "environment": "mock",
  "expected_environment": "mock",
  "logical_account_id": "primary",
  "account_binding": "not_proven",
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

## Failure and recovery contract

- A login/security-control page returns `status=auth_required`; the template
  stops and waits for the user. It never fills a password.
- A correctly identified environment without a proven fund-account binding
  returns `status=unknown` from `probe` with
  `status_reason=account_fingerprint_not_proven`; it is not readiness for a
  write.
- `prepare` compares every requested code, side, quantity, price, date and
  trigger-time field with the actual page readback. A mismatch is a
  `capability_gap`; a matching form is still not submit-ready unless the
  account binding is proven.
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

- The page exposes only a masked login-account hint; a stable fund-account
  fingerprint for `logical_account_id=primary` is not proven.
- The current runtime has not proven a stable strategy/order/deal receipt
  chain, quantization cancellation finality, mixed-account ownership, T+1
  semantics, or authoritative market-state timestamps.
- The manual order route contains an opaque account segment. If the page does
  not expose exactly one same-origin link to that route, the adapter records
  the manual surface as unavailable; `can_withdraw` remains `null` because no
  row-level cancellation fact has been proven.
- The opening-auction route does not natively express
  `min(frozen_open * 1.005, basket_price)`.
- Pagination/virtual-scroll scans are bounded at 100 pages/steps and remain
  incomplete when the page exposes an ambiguous control or fails to reach a
  terminal boundary.
- The mock manual-limit route has previously redirected to the account page;
  that route is reported as a capability gap rather than being treated as a
  successful form.
