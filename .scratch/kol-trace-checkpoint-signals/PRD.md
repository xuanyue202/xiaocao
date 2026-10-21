# Preserve native observation semantics in the action trace

Baseline9e24dd5042ed7e97a512bd05f9a67a1901fc5c76.
During the authorized Oct18 original capture, READINESS relayed the structured
activation request. Its instructions name window errors and security states;
the exporter incorrectly treated quoted code/schema text as an observed native
error, setting first_tool_error_call_id to a successful readiness call.

Checkpoint outputs must retain exact source call IDs/times and hashes, but must
not supply observed WeChat window/security/error signals. Actual native tool
input/readback errors and abnormal/security states must remain observable.
Pending output and incomplete coverage rules, privacy redaction and immutable
snapshots stay unchanged. Re-export the same exact current journal and binding;
preserve old snapshots and do not repeat native operations for telemetry.

This is an offline exporter repair during the same original download. Do not
change or restart capture/backend/PAC, recreate media/tasks, or infer a WeChat
protection cause. Independent Standards and Spec reviews are required.

Validation 2026-10-21: red regression reproduced the checkpoint false positive;
all 14 focused trace tests pass after repair. Independent Standards and Spec
reviews of baseline 9e24dd5042ed7e97a512bd05f9a67a1901fc5c76 and these four
scoped files returned zero remaining findings. Same current Oct18 journal slice
was re-exported without new native actions: 23 complete selected calls, no
pending outputs/coverage limitations, observed error/abnormal/security null.
Old immutable snapshots remain. This is not proof of a protection cause, absence
of unlogged failures, completed media transfer or E2E Handoff.
