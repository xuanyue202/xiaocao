# Audit and repair the complete morning chain

Status: implementing
Baseline: 2749cb7568b3a4abec66ddb8ef8c4e67e32b3cda
Historical redesign review: b89d52dc6b4619df4b21f4a858c91f8742851ee4..2749cb7568b3a4abec66ddb8ef8c4e67e32b3cda, morning current-review modules only.

User request 2026-11-05: diagnose why KOL preview still requires current applicability review, identify exact missing conditions and latest Xiaocao source coverage, repair from first principles; inspect the whole prior design and actual producer/Paper/APP morning execution. Separately schedule one read-only 10:00 counterfactual review of both dates' blocked candidates.

Acceptance:
- Audit exact immutable original runs/owners/shared prep/registration/dispatch and outcomes. Distinguish intentional reviewed no-effect deferral from a failed delivery or completed neutral judgment. Do not replay business or remove COLD/permissions.
- Repair demonstrated CLI wait conflict: validate/reuse the original loaded receipt and timestamp; reject altered owner/source/early-packet or late loading. Exercise actual CLI after registration.
- Every rolling producer preview checks original viewpoint expiry and current local source fingerprint even with no applicable preference. Preserve original frozen bytes and policy authority; cache-only observation never claims remote freshness.
- Explain latest registered Xiaocao report coverage using existing typed selector, with counts/reasons, without widening the model input set or changing published evaluations. Render specific unresolved conditions and clarify that no automatic later review is running.
- Preserve all today's original receipts and recommendation bytes; verify fixes using isolated future-path diagnostics, not another producer or actual policy.
- Independent Standards and Spec scoped reviews, focused pure tests, instruction/automation/runtime packaging alignment; preserve unrelated WIP. Commit/push this coherent KOL repair after validation.

No semantic tradeoff is silently selected: prior full Sol-current judgment benchmark failed09:27. The existing reviewed no-effect deferral and account/source/independent publication gates remain unchanged. A green wrapper or local source check does not prove general current judgment deadline readiness.
