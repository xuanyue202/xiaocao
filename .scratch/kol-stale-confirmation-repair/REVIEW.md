# Review and validation

Baseline e9b2ebfd0a17265826f8e43acf40131d2c383414; scope in PRD.

Independent Spec found caller-time freshness could consume a stale claim. Independent Standards found the same issue and caller-selected claim paths could evade dispatch deduplication. Fixed: module-root/capture-derived canonical path, claim-authoritative30s expiry and exact time equality; all three prompt anchors have stable geometry. Both reviews rechecked and closed all blocking findings before native input.

Three preparation tests failed before implementation.26 Node controller/runtime cases and21 scoped Python request/start-preparer checks pass. Counterexamples cover wrong brand/security/ambiguity/moving controls, copied claim, refreshed caller time, mismatched point and an uncertain input consuming its sole dispatch. Tests copy actual runtime modules into isolated temporary roots; no production UI/network/download side effects.

Real Cancel/readback/native media/cloud/Handoff and historical gap outcomes remain pending. No test establishes a WeChat protection cause.
