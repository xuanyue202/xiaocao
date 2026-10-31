Status: Validated
Baseline: 78c5c786a76e9a54930803c8e31482777c1269ab

Human request: 下次提前2分钟应该就要开始扫描，而且最好能拿到7点那个锁。

At 06:58:00 Beijing the existing local capture invocation must immediately scan under the 07:00 hour lock and sweep slot. Use one shared two-minute early slot rule for all hour boundaries, including date rollover. At 06:57:59 local capture remains outside its daytime window. Preserve actual event times and course replay readiness gates. Preserve retained PTY, source locks, busy behavior and all exact-once claims. Do not alter the remote writer daytime window or active automation cadence/model. Sync skill and existing Automation prompt. Verify boundary, lock contention across 06:58/07:00, real local coordinator execution and legacy-lock protection with offline tests. No production recapture or UI needed.

Validation: 280 offline tests passed (slot gate, daily coordinator/CLI, concurrency). Independent Standards and Spec reviews against the baseline both have zero final findings. Spec initially found startup slot recomputation; fixed by retaining the gate-issued slot through CLI/coordinator, with crossing-boundary regression. Existing Automation updated and reopened through API; exact persisted prompt readback matched, ACTIVE, cadence 07/11/21 Beijing, Sol6.1/high unchanged. Production06:58 capture remains to be observed at the next natural trigger; tests made no UI/capture effects.
