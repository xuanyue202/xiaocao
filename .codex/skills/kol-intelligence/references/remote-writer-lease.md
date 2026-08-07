# Remote Writer Lease

Read this only after `daily_remote_handoff_input_required`. It selects an
existing sole-writer task; it never authorizes creating a task or duplicating a
handoff.

## Twenty-four-hour selection

1. Prefer the newest matching KOL writer Automation task from the current
   Beijing-hour window on `MacBook-Pro-6.local`.
2. If global task/project enumeration times out, or no current-hour task is
   visible, do not stop or ask the user to refresh Codex. Reuse the newest
   directly readable matching writer task created within the preceding twenty-four
   hours. A prior successful task list, accepted-handoff mapping, or Automation
   memory may supply its ID, but `read_thread` must verify the registered host,
   `/Users/xuanyue202/Documents/project/xiaocao` cwd, KOL Automation identity,
   creation time, and current task state before delivery.
3. If the new local thread catalog is empty or its initial build is incomplete,
   discover candidate IDs from the Codex UI remote-summary cache with:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/kol_remote_writer_candidates.py \
     --host-id remote-control:env_e_6a68ce96971c8331b85c5fdf31e38b4c \
     --cwd /Users/xuanyue202/Documents/project/xiaocao \
     --forbid 019fbd59-e55c-7582-8bf9-cb6eee578157
   ```

   This cache proves that a candidate identity was visible to Codex; it does
   not prove current state, delivery, import, or acceptance. Try candidates
   newest-first and still require `read_thread` before sending. Never report
   “no task exists” while the cache contains a matching in-lease candidate. If
   `read_thread` returns `No handler registered`, enter bounded handler recovery:
   confirm the remote device/project layer independently, inspect the current
   Codex Desktop/app-server health and same-call logs, retry the registered task
   handler once after a safe control-plane refresh, then retry `read_thread` on
   the same newest candidates. This is an Agent-owned technical fault, not a
   reason to stop at the first error or ask the user for a retrospective.
   Restarting the whole Desktop app or killing unrelated active tasks is not a
   safe refresh and requires separate authority. A handler error never
   authorizes an unverified send, cache-only delivery, a new task, or a second
   handoff.
4. Prefer an idle task. A matching active task is eligible when it is not
   waiting on approval or user action; queue the follow-up on that same task so
   it remains the sole writer. Never use the forbidden long-lived task, a task
   older than twenty-four hours, or an approval-waiting task.
5. A task-list handler failure alone is not a user blocker. After bounded
   handler recovery is exhausted, preserve the exact unsent handoff as a
   retryable control-plane wait. Report a user-action blocker only when direct
   evidence says the Remote device itself is disconnected or the remaining
   recovery requires restarting/re-registering user-owned Desktop state. No
   candidate may be selected until `read_thread` verifies it.

## Delivery and readback

Send the complete credential-free capsule fields once, never its local path or
video bytes. If send/readback is uncertain, direct-read the selected task and
reconcile the exact task and `handoff_id` before retrying. Do not fail over due
to delay. Once `accepted|already_present` is authoritative, immediately return
acceptance to the same local process; downstream work continues independently
in the selected remote task.
