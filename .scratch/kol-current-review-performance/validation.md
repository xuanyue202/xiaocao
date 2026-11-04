# Validation and limits — 2026-11-04

Baseline: `7a206400e7460c5a79ae64f3c9e1f88273a6c4d3`.

## Actual runs

All performance runs are local isolated engineering replays. Original historical checkpoint availability anchors and actual elapsed wall time are retained. No production policy/account mutation or broker operation. APP-marked checks ran in the permitted lunch test window.

| Path | Preparation | Frozen current work | Independent review / publication | Outcome |
| --- | --- | --- | --- | --- |
| 2026-10-30 APP full Sol xhigh | current preload169.6s; accepted shared source660.211s from prior measured run | judgment68.678s after5.133s handoff | draft09:27:04.587, no publication | Failed original09:27 cutoff |
| 2026-10-30 Paper full Sol xhigh | current preload177s; same shared source | judgment109.820s after6.017s handoff | draft09:27:46.602, no publication | Failed original09:27 cutoff |
| 2026-11-02 APP existing accepted auction WAIT template | template load2.902s; accepted shared source661.108s from prior measured run | materialization/handoff5.857s | parent approved25.711s from freeze; source verification/publication0.620s | consumer validated26.535s; published09:26:04.678 |
| 2026-11-02 Paper same WAIT template | template load2.883s; same shared source | materialization/handoff6.734s | parent approved25.779s from freeze; source verification/publication0.612s | consumer validated26.467s; published09:26:04.706 |

11/2 had7 candidates including one ACTIVE. Auction WAIT changes new exposure from the baseline50% candidate target to0; no fabricated mode/sector mapping, rank alpha or post-open acceptance. Current parent review actually read the materialized drafts, exact requests/account-risk and final Nov1 source. Parent review+orchestration interval was about19.85s APP /19.05s Paper; measured as final handoff-to-approval, not pure model compute. Source-only preparation was independently measured/sealed earlier, reused here rather than re-estimated. Publication used archived exact report heads/manifests through the normal publisher; live-provider latency is unmeasured. Original consumer acceptance is proven; broker/order execution and historical account reconstruction are not.

11/4 real Paper account/positions byte-copy:245rows,0open B lots, original child0.221369s, strict JSON and NORMAL risk; production hashes unchanged. Separate tests reject closed-lot economic NaN and concurrent raw-byte changes. Sparse shared CLI4.089946s total,0network attempts,34unchanged+10added viewpoints, no semantic synthesis worker; this is packet construction, not a full sparse publication benchmark.

Artifact root: `output/kol-current-review-performance/` (excluded from commits). Preserve formal1/2/3 failed/aborted attempts and plumbing-only fixtures; never count fixtures as real model timing. formal3 and template result.json are the respective actual evidence. No original request replay, deadline reset or late publication.

## Quality loop

Independent Standards review found one economic finite-validation regression. Independent Spec review found it and a preload-error cold-fallback regression. Both fixed; independent affected-diff re-reviews report no remaining actionable source issues.162focused tests passed2.31s;115runtime/context/risk tests passed13.19s;53APP morning/runtime snapshot tests passed0.75s. Shell syntax and diff whitespace passed. Full suite and actual native APP orders were not exercised.

## Pending user decision

Complete-current Sol judgments failed deadline despite preloading/direct handoff. User has been asked to choose pre-reviewed conditional branches with fresh predicate checks (unresolved/new semantics explicitly degrade), or retain full post-freeze judgments accepting missed cutoff dates. No new semantic tradeoff has been implemented. Successful11/2 existing WAIT template does not prove general09:27 readiness.
