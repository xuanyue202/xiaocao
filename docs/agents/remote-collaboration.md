# Codex Remote dual-machine collaboration

`MacBook-Pro-6.local` is a normal, long-lived Xiaocao collaborator reached through **Codex Remote**, not through local mDNS, LAN SSH, AirDrop, or an ad-hoc filesystem inbox. The local repository is `/Users/bytedance/coding/xiaocao`; the remote repository is `/Users/xuanyue202/Documents/project/xiaocao`. Reuse the registered remote Xiaocao project and its existing cutover/executor task whenever possible.

Keep these connectivity layers separate and report the narrowest failing layer:

1. **Remote device** — the Codex UI showing `MacBook-Pro-6.local` with a green `已连接` status proves the remote-control host is connected.
2. **Project discovery** — `list_projects` proves whether saved projects were enumerated for that host. An omitted project or `No matching saved project` does not prove the host is offline.
3. **Task discovery/readback** — `list_threads`, `read_thread`, and `wait_threads` prove whether a particular task can be enumerated and read. `thread_list_unavailable`, `No Codex thread found`, or a stale task handle is a task-service/handler failure, not host-offline evidence.
4. **Runtime readiness** — Git SHA, worktree state, dependencies, private config, restored state, and Automation readback prove whether Xiaocao may run there. Host connectivity alone never proves runtime readiness.

When the Remote device is connected, continue normal coordination through Codex task messaging and authoritative readback. Do not downgrade the host to “offline” merely because project/thread enumeration fails, and do not use `.local` DNS, `ping`, or SSH failure to contradict a green Codex Remote connection: the normal control plane may be cross-network and independent of LAN discovery. First retry the registered host/task directly, distinguish an accepted-but-unread message from a completed task, and reconcile the exact task identity before retrying any state-changing instruction. Ask the user to reopen Codex, re-register a project, or touch the remote machine only when the Remote device itself is disconnected or the remaining handler failure truly requires user action.

Dual-machine business safety remains fail-closed: GitHub `main` is the code SSOT; WeChat-dependent capture stays local; KOL and simulated-trading writers move only after the remote SHA/runtime/state and authoritative Automation ownership are read back. Never allow active-active writers, never start a remote business writer before state restore, and never infer an Automation switch from checked-in TOML mirrors.
