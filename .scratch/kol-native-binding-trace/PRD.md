# Native binding errors must remain visible

Status: Complete

## Problem and evidence

The Oct21 evening original retains three actual WeChatAppEx getApp calls with Computer Use timeoutReached. The exporter currently treats those marked calls as checkpoints and suppresses their native error signals. getApp may activate/launch an application; it must not be described as passive observation.

## Scope and acceptance

- Recognize observed WeChat application binding targets (main bundle and mini-program host bundle/path) in cua_repl calls, including an unmarked binding call.
- Classify binding as native_binding, preserving actual request/output bounds and credential-free hashes, and include it among preceding effects without causal attribution.
- Recognize actual Computer Use timeoutReached as a tool error; checkpoint instructions containing that text remain non-observations.
- Keep unrelated browser/checkpoint text from classifying as native WeChat state. No native operations or retries for telemetry.
- Re-export the same exact existing journal and original IDs; preserve immutable old snapshots.
- Record this run's bounded bridge reconstruction success as workflow evidence, not a proven WeChat protection cause or an unconditional retry.
- Focused regression and independent Standards/Spec review against baseline 6f8a8b14a06728055ae3726f88ed9dac7b6c2e26.

## Validation

23 focused regression cases passed; independent Standards and Spec reviews each reported zero findings. Re-export of the same exact original journal retained 91 completed calls, no pending outputs, selected_calls_recorded coverage. All three original WeChatAppEx binding timeouts now remain native_binding / timeoutReached with unchanged source-call IDs. Old immutable snapshots remain. No additional native operation was performed for testing. Tonight media is still downloading; these checks are not Handoff or protection-cause acceptance.
