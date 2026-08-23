# Founder Securities Web/OpenCLI read-only route

Use this branch when inspecting or validating the versioned Founder Securities
browser templates under `opencli/clis/foundersc-quant/`.

## Run order

1. Verify the checked-in template manifest:
   `python3 scripts/install_opencli_foundersc_quant_template.py`.
2. Install only after an explicit user request:
   `python3 scripts/install_opencli_foundersc_quant_template.py --install`.
3. Run `scripts/foundersc_keychain_preflight.py` when credential readiness or
   the masked login-page binding must be checked. `--read-secrets` is bounded
   and must remain outside unattended automation while it reports an ACL
   prompt.
4. Use `probe`, then the needed `environment`, `prepare`, `reconcile`, or
   `recover` command.
5. Treat `unknown`, `capability_gap`, and `reconciled_partial` as readback
   gaps. Reconcile the same session before any future action.

## Current contract

The templates are no-submit phase-one adapters. They do not read credentials,
save or start strategies, submit orders, or withdraw orders.
`environment` may change only the unique mock/live switcher and must verify the
exact target environment readback; it is not a submit route and should be
restored to mock after an isolated live-page probe. `submit_capability=false`
remains the hard gate. Account binding is not proven unless the page supplies a
stable fund-account fingerprint, so a complete page scan is not a formal Book
B readiness proof by itself.

Pagination and virtual lists must be scanned to a proven terminal boundary.
An absent table, loading shell, non-unique route/container, ambiguous next
control, or incomplete scroll must remain incomplete rather than becoming a
successful reconcile.

The manual route must be discovered as exactly one same-origin opaque
`#/home/orderByHand/<account>/entrustDetail` link. A base
`#/home/orderByHand` route is not sufficient. Form preparation must compare
every requested field with its page readback and close only through the exact
read-only cancel control.

This branch has no Codex Automation. The implementation PRD explicitly keeps
the current automation and paper writer unchanged until a separate route and
activation gate are approved.

The Xiaocao phase-one adapter writes only broker-ownership evidence and
execution/takeover receipts. `positions.jsonl`, `paper_trades.jsonl`, and
`paper_ledger.lock` remain the canonical paper account boundary; an ownership
evidence file must never be configured as one of those paths. The execution
port also fences one `logical_account_id` at a time and persists a
credential-free takeover capsule whenever an incident or UNKNOWN state needs
human/reconcile intervention.
