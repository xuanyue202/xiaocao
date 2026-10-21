# Safe transport evidence for native capture

Baseline dfb12e8e4f430e3f4b1461a1623c880bde974f2b.
User explicitly requested logs/root diagnosis of observed WeChat security exits.
Existing Echo default logger and default TLS server errors are discarded; raw
logging would leak signed media URLs. Add a capture-only allowlisted sink after
Echo initialization, without modifying routes, MITM scope, native actions or
credentials. Restore sink/close journal on stop or failed start.

Private0700directory,0600unique per-process journal; only timestamp,PID,random
process-run id, enumerated kind/coarse target group and coverage counters. No raw
line,URL,path/query,host,header/cookie/body,typed text or credentials. Classify
trusted log prefixes, not payload words. Actual CONNECT templates must map to
correct groups. Bound8MiB/16KiB message processing; explicit caps and write/short
write failures remain visible as coverage loss. Close must not invert standard
logger/own mutex order. Tests include real rejected local TLS, concurrent close,
malicious query text, secret-bearing raw lines, cap/unknown/oversized and storage
failure. No new runtime dependency. Package checked additive sources/integration
and helper; install only after current video completed-cleanup gate.

These observations do not establish WeChat internal cause or full coverage of
DIRECT traffic. Open/partial/zero-event/capped/failed/unclassified journals are
evidence_incomplete. Native per-call trace remains separate and authoritative
for dispatched inputs/readbacks. Never reproduce native protection for telemetry.
