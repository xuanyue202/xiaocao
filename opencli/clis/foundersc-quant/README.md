# Founder Securities OpenCLI templates

Template version: `8`
Site: `foundersc-quant`
Scope: secure Edge persistent-session login, route-aware
probe/preparation/reconciliation/recovery, verified mock/live environment
switching, and one package-limit submit route.

These templates are the browser-side adapter surface for the Xiaocao
`BookBLiveExecution.execute(plan, broker_adapter)` seam. Only the observed
`package-limit` route exposes a write command. `manual-limit`, `opening-auction`, and `timed-order`
remain no-submit routes; a page field or a
successful navigation is not a broker receipt.

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
  --route package-limit \
  --expected-environment mock \
  --logical-account-id primary \
  -f json

opencli foundersc-quant environment \
  --target live --expected-current mock \
  --logical-account-id primary \
  -f json

opencli foundersc-quant prepare \
  --route package-limit \
  --expected-environment mock \
  --logical-account-id primary \
  --code 600000 --side buy --quantity 100 --price 10.00 \
  -f json

opencli foundersc-quant submit --route package-limit \
  --expected-environment mock \
  --logical-account-id primary \
  --expected-fund-account-fingerprint '123******789' \
  --claim-id bookb-20260824-001 \
  --strategy-name XC0824 \
  --code 510300 --side buy --quantity 100 --price 4.22 \
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
The receipt makes these paths mutually exclusive:
`session_reuse_proven=true` means only that an existing authenticated session
was proved; `fresh_login_proven=true` additionally requires an initial
`login_required` state, a successful fixed-Keychain read, unique form binding,
exactly one login click and a post-click authenticated readback. Neither field
proves native PassGuard trade-password recovery.

`probe` defaults to `--route package-limit` so callers that omit the route
remain compatible. It opens the package create page and reports
`submit=true` / `submit_capability=true` only when the exact empty create-page
DOM and account/environment binding are proven. `receipt_mapping` remains
false until a trading-hours response proves the broker order-id shape. The
production engine permits only one durable-claim canary submit after every
other gate passes; that same submit must prove account binding, order-id,
strategy-id and receipt mapping or it becomes UNKNOWN/reconcile-only without a
second click. Any submit-uncertain plan stays ineligible for automatic
replacement even if a later readback is partial; the engine applies the same
block to prepare/reconcile uncertainty. Reconcile must map the same captured
order-id while preserving its submit strategy-id evidence. An unmapped reject
is terminal only with no-click/no-save/no-start proof. A never-ambiguous first
order may receive at most one controlled replacement only after exact
terminality and fresh-market proof, with two total attempts enforced at the
submit boundary. Explicit probes for `manual-limit`, `opening-auction`, or
`timed-order` report all write capabilities as false.

`prepare` supports `manual-limit`, `opening-auction`, `package-limit`, and
`timed-order`.
Manual limit never clicks `买入` or `卖出`; because the observed page does not
prove a separate non-submitting side selector, `prepare --route manual-limit`
reports a capability gap instead of claiming the requested side was selected.
Package limit opens `组合交易 -> 按证券组合 -> 添加证券`, uniquely selects the
visible `.al-modal-container`, fills `stockCode`, 买入/卖出, `指定价格`, numeric
price and quantity, reads every field back, and clicks only the exact
`.al-modal-cancel-button`. It then proves the modal is closed and the create
page still says `暂无数据`; it never clicks the add-modal confirmation, 保存, or
下单.
Opening auction opens the form, fills only the requested fields, reads them
back, and closes the empty form with its exact `取消` control. Timed order must
first prove that the requested numeric limit is one native price option. The
observed timed-order widget instead offers quote-derived values such as
`现价`, `买一`, `卖一`, and `开盘价`; writing a decimal into its inner input does
not select the Angular model. In that shape `prepare --route timed-order`
returns `timed_order_numeric_limit_not_supported` and closes the form. The
other read-only routes never click `保存`, `启动`, or `确定`.

`submit --route package-limit` is the sole write route. It first proves the
expected environment and masked fund-account fingerprint, reads the strategy
list, and rejects an already-used exact strategy name. Names are limited to
eight letters/numbers/CJK characters, `_`, or `-`. It then uses only trusted
UI controls on `#/home/packageDeal/create?type=security`: add one security,
select `指定价格`, confirm the local row, verify the exact code/name leaf and
numeric `input#input-inline-0` / `input#quantity-0`, and check the unique
security and the unique `.risk-agreement-link input[type="checkbox"]` controls
before clicking the unique `下单` button. The security checkbox must
independently be the only `input[type="checkbox"][id="<code>"]`; header,
suspension, and other checkboxes never satisfy either proof. If the click opens
the observed `名称设置` modal, the command then fills and reads back the unique
`input#name[name="newName"]` and clicks the modal's unique `确定` control. It
does not assume that the strategy-name input exists on the create page.
`claim-id` is a required bounded caller correlation id returned as `task_id`;
it is not used as the strategy name or broker order identifier.

The browser interceptor observes, but never directly calls, the page's
first-party `preEntrust`, `save`, and `entrust` responses under
`/qt/packageTask/{mock?}/`. The first click must yield one successful
preEntrust response and one exact `确定提交委托？` table before the command clicks
its unique `提交` control. A success requires one stable strategy id from save,
one stable order/entrust id from a known entrust-response field, one successful
entrust response, the `下单成功` UI, and exactly one post-submit strategy-name
match. A known non-trading response is `status=rejected` with
`submitted=false`. Once the final submit click may have happened, any missing
or ambiguous receipt is `status=unknown`, `submitted=null`, and
`reconcile_required=true`. The command never retries a write click.

For no-order diagnosis, `submit --preflight-only true` follows the same
account-bound form and first-party `preEntrust` validation but stops before the
`确定提交委托？` server-confirm control. It clears the local draft and proves
`submitted=false`, `saved=false`, `started=false`, and final-submit click count
zero. It also validates the current official confirmation model's single
`ul.scroll > li` entrust row (with the legacy single table row retained as a
fail-closed compatibility shape), but never clicks its submit control. Known
pre-entrust failures are reduced to fixed categories such as
`gem_permission_missing` or `agreement_required`; raw broker response messages
and bodies are never returned. This mode is diagnostic evidence only and can
never be treated as an accepted order.

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
  "template_version": 12,
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
page has no exact order-id-bound row or the visible table does not expose the
identifier.
`field_readback` contains only the requested form fields and sanitized page
facts. It does not infer a fill, order id, status mapping, basket rule,
T+1 ownership, or retry permission. An exact current-day reconcile may return
`filled_shares` and `remaining_shares` only when a previously captured broker
order id uniquely maps the order row and any fill rows; a missing order id,
duplicate row, wrong date, or incomplete fill legs remains UNKNOWN.
`observed_at` is the local template readback time, not a broker event timestamp.

## Strategy-surface decision

The Founder UI surfaces inspected for the Book-B route are:

- condition strategies: `止盈止损`, `定价单`, `移动止损`, `底部反弹买入`,
  `顶部下跌卖出`, `定时单`, `通用回购逆回购`, `分批建仓`, `分批清仓`,
  `指数跟随`, `定投单`, and `开板卖出`;
- grid strategies: `基础网格` and `高级网格`;
- single-security algorithms: `TWAP`, `VWAP`, `冰山`, `黑色冰山`,
  `价格分段`, and `时间分段`;
- combination algorithms: `TWAP_PRO`, `VWAP_PRO`, `POV_PLUS`, `POV_PRO`,
  and `盘前集合竞价`;
- combination trading: `按证券组合`, `按交易金额`, `按交易份额`, and
  `按当前持仓`.

Backtest and multifactor pages are research surfaces, not order routes. The
selected production candidate is `组合交易 -> 按证券组合 -> 添加证券 -> 指定价格`:
it is the only observed surface that expresses one exact numeric limit and one
exact board-lot quantity for each security without changing the order into a
threshold trigger, quote-relative price, recurring schedule, auction policy,
or sliced execution algorithm. This is the closest faithful representation of
Book B's `min(frozen_open * 1.005, basket_price)` one-shot initial order.
Selection of the route does not prove trading-hours submission, broker order-id
shape, cancellation finality, or the at-most-one retry policy.

For a successful package-limit command, `strategy_id` is the bounded id from
the save response, `order_id` is the bounded id from an explicit known
order/entrust field, `submitted=true`, and `started=false` because this is an
immediate package order rather than a started scheduling strategy. Fills, deal
finality, and cancellation finality remain unproven, so the receipt still
requests downstream reconciliation. Receipts contain only the masked account
fingerprint and canonical status codes, never intercepted response bodies,
raw accounts, passwords, cookies, or security-control values.

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

Template v12 carries a known broker order id across trade dates: it binds the
historical-order and historical-deal tabs to the exact immutable plan date,
captures only `/qt/user/historyEntrust`, and requires the same unique visible
tuple/status plus API order-id mapping before returning a terminal or active
receipt. An incomplete or broad history filter remains reconcile-only.
Template v11 retained v10's strict broker order-id mapping and retries the
read-only visible-table scan and intercepted `/qt/user/todayEntrust` capture as
one bounded unit after a fresh-page navigation. A cached fresh site session
therefore cannot turn a complete visible row with an absent capture into a
false broker outcome; exhaustion remains reconcile-only. Template v10 retained
v9's credential-free response-shape diagnostic and maps
the read-only `/qt/user/todayEntrust` response only when its stable broker
`orderId` is bound to the already-claimed strategy id, exact code, quantity,
and price, while the visible current-order table independently has one exact
code/side/quantity/price row with the same normalized status. Duplicate
captures are deduplicated and raw responses, account values, and task names are
never returned. Missing or ambiguous strategy/order ids, tuple rows, response
fields, status agreement, or zero-fill proof remain reconcile-only. Template v8 added a prior-day,
read-only absence proof. For a plan that remains UNKNOWN without a broker
order id, `reconcile --scope settlement` selects the exact prior trade date
on both historical-order and historical-deal tabs, queries each once, scans
their terminal table states, and combines zero related rows with a complete
current asset scan proving zero target holding. Only that exact account-bound
combination returns `prior_day_broker_absence_proven`; a same-day plan, broad
date range, incomplete/ambiguous table, related order/deal, or target holding
remains reconcile-only. The proof never calls a broker API directly and never
clicks submit, save, start, or withdraw.

Template v7 also exposes a strict `allocation_summary` from either one unique
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
- `submit` rejects an environment/account mismatch, duplicate exact strategy
  name, non-unique DOM, non-numeric readback, unchecked required checkbox, or
  unproven server confirmation before its final submit click.
- Explicit preEntrust non-trading failures return `rejected` and
  `submitted=false`. Missing captures are not treated as rejection.
- After the final `提交` may have been clicked, exceptions and incomplete
  save/entrust/UI evidence return `unknown`, `submitted=null`,
  `retry_allowed=false`, and `reconcile_required=true`; callers must never
  retry that intent.
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
- There is no withdraw action in this version. `cancelled` remains false for a
  form that was merely closed; `form_closed` means the empty preparation
  dialog was closed locally, not that a broker order was cancelled.

## Known evidence gaps

The templates preserve the research gaps rather than hiding them:

- The page parser requires exactly one numeric fund account from either the
  exact visible `资金账号` label or the authenticated same-origin base-info
  response. If that masked fingerprint does not match the Keychain
  trade-account metadata, `logical_account_id=primary` remains unproven and
  live allocation facts are not emitted.
- The current runtime has code for the observed package save-id and entrust
  acknowledgement chain, but the live-market final-submit branch is still
  unverified. Stable broker order/deal identifiers, cancellation finality,
  mixed-account ownership, T+1 semantics, and authoritative market-state
  timestamps remain unproven.
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
