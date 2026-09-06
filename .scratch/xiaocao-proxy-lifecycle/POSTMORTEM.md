# macOS capture proxy lifecycle repair — 2026-09-06

Status: implemented; deployed locally; validation recorded below.

## Symptom and evidence

User reports intermittent loss of network access after using the wx downloader;
starting it again and pressing Ctrl+C restores access. At inspection no capture
process/listener remained and all four effective proxy flags were zero. This was
not an active outage, so the historical exit signal cannot be identified.

The isolated regression drives the real `cancel_capture_wait` path with an owned
PAC enabled. Before repair it fails before SIGINT with:
`AssertionError: network still points at the proxy being stopped`.

Repro: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_kol_xiaocao_live.py
-q -k cancel_wait_stops_only`. Initial result: 1 failed, 1 passed. Repaired result:
both pass. System proxy operations are simulated in this regression.

## Five whys and verified code causes

1. Network clients can still send traffic to a loopback proxy with no listener.
2. macOS network-service proxy preferences persist beyond the downloader's life.
3. Cancellation omitted PAC detachment; the Go capture-only stop path did not
   own the agent-applied PAC. Ctrl+C in full proxy mode disabled HTTP/HTTPS only.
4. Root handled SIGINT/SIGTERM but not SIGHUP; process death bypassed in-process
   cleanup. Device selection was recalculated at stop; Python inspected only
   the current effective PAC before scanning services, missing old networks.
5. Proxy ownership was spread across agent/Python/Go without an independent
   lifetime-bound recovery owner. Tests began with PAC already off, hiding this.

These mechanisms explain the workaround; they do not prove which one caused
each earlier user-observed outage. No WeChat protection event is inferred.

## Repair and boundaries

- Cancel detaches only the exact capture PAC on every configured service before
  SIGINT; singleton discovery excludes only exact `__proxy-guard` invocations.
- Go binds/listens before enabling system proxy, pins the selected service and
  acquires a detached pipe-leased restoration helper before mutation. It keeps
  an ownership lock through cleanup, preventing old cleanup/new run races.
- Guard snapshots HTTP/HTTPS/PAC, restores exact owned endpoints, preserves
  later foreign/VPN changes, checks readback, and logs failures. No credentials
  are read; taking over an authenticated global proxy is rejected.
- SIGHUP uses graceful cleanup; EOF from SIGKILL/panic also releases the lease.
  Failure in one proxy field does not prevent independent fields being cleaned.
- No-op writes and partial restore errors cannot be called success. A timeout
  cannot prove endpoint absence. Explicit `proxy-recover` requires refused TCP
  connection and no active lease, disables only exact legacy orphans, and starts
  no capture/API/server. It does not guess the original settings of an old run.
- Existing capture PAC adds `; DIRECT`. This preserves connectivity on a failed
  proxy path, not capture success; original exact-media acceptance still applies.
- No permanent daemon/LaunchAgent/Automation, VPN shutdown, login/security hooks,
  WeChat UI action, or capture/upload/mailbox replay was introduced.
- Power loss, killing both parent and guard, unavailable networksetup, and a live
  but unhealthy forwarding engine remain outside a universal cleanup guarantee.
  For leftover settings use explicit recovery; guard errors are not hidden.

## Versioning and deployment

Go repair is local commit `5f15827c023fbee3dbce797e7f682cd7d3133bda` in
`/Users/bytedance/coding/wx_channels_download`, not pushed to the third-party
remote. Only repair hunks were staged; existing capture-only and other worktree
changes were preserved. The existing capture-only PAC's one-line DIRECT update
is retained as a separate patch in this folder, because its parent function is
part of the pre-existing uncommitted work, not part of that repository's HEAD.
The patch is applied with `git apply --unidiff-zero`; its reverse check passed
against the deployed worktree, proving the DIRECT change is already present.

Installed binary: `/Users/bytedance/coding/wx_channels_download/wx_video_download_macos_arm64`

- New SHA-256: `3eac45e32311a8aa0305237317153429ba328477396566c345f9d45ab953f4f4`
- Backup: `wx_video_download_macos_arm64.before-proxy-guard-20260906`
- Backup SHA-256: `c136881020d335a2825f16a2cb375214fe3b701fd39f5370486215bafa8dec7c`

Xiaocao fast-forwarded to remote `1ae1581` before committing this repair.
Unrelated 53-line deletion in `tests/test_kol_lv_subscription.py` was restored
unchanged after integration; a safety stash `8689033180ef5b88427bbed147cfcaf21a958a3b`
was retained. No runtime business state was replayed or hand-edited.

## Verification

- Go unit/subprocess tests replace only networksetup: real parent/guard pipes,
  locks and signals; SIGINT, SIGTERM, SIGHUP, SIGKILL each passed 10 repeated
  cycles (40). Restores original PAC URL/enable state and preserves foreign proxy.
- `go test -race ./pkg/system ./internal/interceptor ./internal/manager ./cmd`
  passed. The isolated staged tree also passed tests/build without relying on
  the unrelated dirty worktree.
- Pre-integration Xiaocao capture/transfer/daily suite: 308 passed.
- Real built binary started in capture-only mode with system proxy kept off;
  API/PAC were read, the independent helper existed, and Ctrl+C closed both
  processes/listeners with verified restoration. No WeChat UI was operated.
- Standalone recovery succeeded with no active proxy; non-loopback target was
  rejected with exit code 1. Additional installed-binary and final merged-tree
  checks are recorded in the completion update.

### Completion update

- Final merged-tree Python suite including skill-structure contracts: **366
  passed in 3.97s**. Added cancellation with PAC on/off, inactive/disabled network
  services, no-op-write rejection, and exact guard/singleton differentiation.
- Installed binary PID 28398 and guard PID 28464 were observed. SIGHUP to the
  owned parent produced `下载器已关闭，代理恢复已验证`, exit 0. Both PIDs then
  disappeared; ports 2022/2023 closed; HTTP/HTTPS/PAC/SOCKS flags all read zero.
- Wi-Fi's original `http://127.0.0.1:33331/commands/pac` remained configured and
  disabled. Installed binary hash matches the recorded new SHA-256 above.
- No live proxy was enabled for testing. Persistent-network restoration under
  SIGKILL was exercised with real OS subprocesses and simulated networksetup,
  not by deliberately interrupting the user's network.

Primary platform reference: https://go.dev/pkg/os/signal/ (SIGKILL cannot be
caught in-process, hence recovery must survive outside the terminated process).
