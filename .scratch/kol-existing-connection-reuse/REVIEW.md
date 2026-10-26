# Review and validation

Baseline154b506. Scope: PRD, shared Python hold reader, source reader refactor,
Liuguan runtime/CLI/companion, two affected regression files and Liuguan docs.
Independent Spec and Standards reviewed the explicit working diff plus new files;
both returned no blocking findings. No review ran production UI/network probes.

Before repair, the real companion regression requested native initialization
while held; direct bootstrap reached native lease acquisition. Both were observed
red. After repair271 affected Python tests and10 source-order/deadline tests pass.
The unchanged backend's3 JS socket/exception/exclusivity tests and Go Channels
client tests passed offline; no backend build, replacement or restart occurred.

Production passive connections command verifies deployed hash/PID39765 and
returns channels_connection_missing, hold=true, backend_started=false and0
native/PAC operations. A prior35s local-only wait did not reconnect. One exact
previously successful publisher's existing list endpoint returns the local400
socket-initialization error, no SDK payload, no retry. API presence/port health
is not an authenticated page. Private diagnosis and exact-api-check JSON preserve
source hashes and original manifest/ledger fingerprints without media credentials.

Existing144 backend tasks remain130done/14paused; the original evening source
is awaiting_playback/awaiting_capture with no bound identity/media/task.1766
candidates contain0 observations since its publication. The catalogue remains
33publishers/276replays/5verified artifacts. No new download/upload/ASR/UI/PAC
work was performed. Native hold remains active; protection cause and real capture
remain unresolved. No unrelated old recording is substituted.

## October24 direct-entry follow-up

Baseline8511466; independent Spec and Standards reviewed the scoped diff in
liuguan-local-discovery.md and liuguan-shared-capture.md, plus private direct-open
readback. Both reported no blockers. Only documentation/instructions changed;
scoped diff whitespace checks passed, no implementation-mirroring tests added.

The bounded LaunchServices probe dispatched once and returned0 without a
verifiable new feed window or socket.144 task records had the same before/after
hash. Limited window/AX observation leaves internal navigation unknown. An
initial read-only baseline used an incorrect task API path and returned404;
it stopped before any native dispatch, then used the existing tasks() reader.
The independent Caoliao draft was not saved/published; its Channels component
requires public channel/video fields not present in the exact cached cards.
These findings neither establish a cold-start route nor resolve protection.
The corrected instructions prohibit Moments/profile/chat/global-search fallback
and distinguish retained-page recovery from an unverified direct homepage open.
