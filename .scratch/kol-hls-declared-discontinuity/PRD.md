# Preserve finite replay across a declared HLS discontinuity

Status: Implemented; same-item production continuation pending

The original Oct20 morning capture stops at 57.6%, near 1068 seconds. The
manifest explicitly declares a discontinuity before segment 217. Exact cache
hashes pass; a fresh segment 216 has identical bytes and individually passes
strict decoding. FFmpeg's HLS demuxer flags a packet corrupt when it joins that
declared boundary. Offline separate HLS demuxers joined by the concat demuxer
pass strict decoding of the same cached prefix. This is not a proven network
failure or WeChat protection outcome.

Split only at source-declared discontinuities, retain original segment order,
media sequence, active encryption/init state and exact per-period durations.
Serve only generated loopback concat/period descriptors, keeping credentials
in the existing backend memory. Preserve strict input decoding, all-segment
hash coverage, full duration within 2 seconds, output decode and Handoff gates.
Never skip/discard packets, infer boundaries, weaken TLS, recreate captures or
tasks, overwrite prior completed artifacts, repeat cloud upload or native input.

Build a separate candidate using hash-bound additive-source upgrades with
reversible backups. Extend the existing stopped-checkpoint replacement guard
to an unpublished original download as well as an explicitly prepared revision:
require exact retained task/output/candidate/live, no active singleton tasks,
non-terminal unchanged cache binding and post-replacement same-task readback.
Published or changed output/identity and user-paused jobs remain blocked.

Resume this original capture/task from its 219 verified segments only after
focused tests and independent Standards/Spec review. Validate the complete
original media, cleanup, existing upload and exact mailbox receipt/readback.

Validation: 37 focused Python media-repair/acceptance tests pass. Go stream,
download, API and interceptor tests pass; same-directory candidate builds with
SHA256 `6653d0f68729443d7ef0eb90bcb8bb092aa964620e0ac97737156c281e164cfb`.
Independent Standards/Spec review against
`cd7fd40091cd02f8ad2877cb76f2eb40723a08f0` found an init-MAP encryption
association omission; preserving the MAP's original KEY plus a rotation
regression closes it. Both affected-diff re-reviews report zero remaining
findings. Offline checks are not media/cloud/Handoff completion.
