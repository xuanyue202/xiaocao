# Founder Securities Web/OpenCLI package-limit route

Use this branch when inspecting or validating the versioned Founder Securities
browser templates under `opencli/clis/foundersc-quant/`.

## Run order

1. Verify the checked-in template manifest:
   `python3 scripts/install_opencli_foundersc_quant_template.py`.
2. Install only after an explicit user request:
   `python3 scripts/install_opencli_foundersc_quant_template.py --install`.
3. Run `scripts/foundersc_keychain_preflight.py` when credential readiness or
   the masked login-page binding must be checked. The user has authorized the
   fixed login item for unattended use after its Keychain ACL is configured.
4. Use `login` to read only the fixed
   `xiaocao.foundersc.quant.login` item. It may pass the phone and login secret
   directly into the unique native login controls, but must never print, log,
   persist, or return either raw value. All other templates remain
   credential-free.
5. Use `probe`, then the needed `environment`, `prepare`, `submit`, `reconcile`,
   or `recover` command. `submit` is allowed only for the exact account-bound
   `package-limit` route and never retries its final click.
6. Treat `unknown`, `capability_gap`, and `reconciled_partial` as readback
   gaps. Reconcile the same session before any future action.

When more than one Browser Bridge is connected, the live-morning runner selects
the single connected context carrying the `default` alias and passes its actual
context id to every command. One connected profile is also unambiguous; multiple
profiles without one `default` alias fail closed as `OPENCLI_PROFILE_AMBIGUOUS`.
The adapter accepts OpenCLI's compact or pretty-printed one-row JSON receipt,
including a short diagnostic prefix, but never parses arbitrary page text.

## Current contract

Only `login` reads the fixed login Keychain item under the bounded contract
above. No template reads or emits the trade password. Template v6 adds one
UI-only `package-limit` submit route; the other routes remain no-submit, and no
route withdraws orders.
`environment` may change only the unique mock/live switcher and must verify the
exact target environment readback; it is not a submit route and should be
restored to mock after an isolated live-page probe. Account binding is not
proven unless the page supplies a
stable fund-account fingerprint from the authenticated same-origin read-only
`/qt/user/getBaseInfo` response. The
browser masks that value before returning from page context, and the Python
adapter must still match it against Keychain metadata. A complete page scan is
not a formal Book-B readiness proof by itself.
Fund-account values shorter than eight digits are redacted but never accepted
as binding proof; that shape remains fail-closed rather than relying on a
collision-prone low-entropy mask.

Pagination and virtual lists must be scanned to a proven terminal boundary.
An absent table, loading shell, non-unique route/container, ambiguous next
control, or incomplete scroll must remain incomplete rather than becoming a
successful reconcile.

The selected candidate is `组合交易 -> 按证券组合 -> 指定价格`, because it can
represent one exact numeric limit and one exact board-lot quantity without
threshold, quote-relative, recurring, auction, or slicing semantics. Condition
strategies, grids, TWAP/VWAP/POV/iceberg, price/time segmentation and auction
algorithms therefore remain rejected substitutes for the Book-B initial
one-shot limit. The manual route must be discovered as exactly one same-origin opaque
`#/home/orderByHand/<account>/entrustDetail` link. A base
`#/home/orderByHand` route is not sufficient. Form preparation must compare
every requested field with its page readback and close only through the exact
read-only cancel control.

This branch is invoked only by the separate 09:20 Book-B live-morning
Automation. That task switches and verifies the live environment, performs a
read-only `reconcile --scope assets`, and emits dated allocation facts only
when the result proves a complete asset scan and exact environment/logical-
account/fund-account binding. Mixed-account totals remain readback evidence;
they never become the Book-B settled-NAV or owned-exposure basis. It then
consumes only a producer-manifest-bound dated snapshot and verifies restoration
to mock on every exit; it never calls or waits for the 09:25 paper task.
The manifest binds the producer strategy Git SHA. The allocation facts bind
their full economic capsule (capital-basis source, Book-B NAV, cash, exposure
and broker summary) under one canonical SHA-256 and require broker-summary cash
to agree with top-level available cash. The live logical account and first
Book-B basis are fixed to `primary` and 30,000 yuan in this phase, with no CLI
override.
Unproven account binding, missing broker allocation facts, missing capital
keys, incomplete reconciliation, or an ambiguous submit receipt remain
terminal fail-closed states. Trading-hours final-submit/order-id proof,
row-level cancellation, Book-B's at-most-one controlled retry, and unattended
native PassGuard recovery are still pending. The paper writer and its
Automation stay unchanged.

Template v6 extracts `总资产` / `证券市值` / `可用资金` from one unique asset
card set or one unique agreeing table shape. It compares the page's masked
fund-account fingerprint with Keychain trade-account metadata in-process,
persists only the binding hash, and rejects missing, mismatched, wrong-date, or
older-than-five-minute receipts. A fixture-shaped Python payload is not
sufficient.

The Xiaocao phase-one adapter writes only broker-ownership evidence and
execution/takeover receipts. `positions.jsonl`, `paper_trades.jsonl`, and
`paper_ledger.lock` remain the canonical paper account boundary; an ownership
evidence file must never be configured as one of those paths. The execution
port also fences one `logical_account_id` at a time and persists a
credential-free takeover capsule whenever an incident or UNKNOWN state needs
human/reconcile intervention.
